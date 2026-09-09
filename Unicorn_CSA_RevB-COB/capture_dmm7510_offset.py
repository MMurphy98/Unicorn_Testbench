#!/usr/bin/env python3
"""Acquire numbered Keithley DMM7510 DCV offset records as verified TDMS."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import re
import sys
import time

import numpy as np
from nptdms import ChannelObject, GroupObject, RootObject, TdmsFile, TdmsWriter
import pyvisa
from pyvisa.constants import AccessModes
from pyvisa.errors import VisaIOError


DEFAULT_TASK_ID = "DUT_RevB_with_PMU"
TDMS_GROUP_NAME = "Keithley DMM7510 Offset"
DCV_CHANNEL_NAME = "DCV"
TIME_CHANNEL_NAME = "ElapsedTime"
NPTDMS_VERSION = "1.11.0"
FORMAT_VERSION = 1


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def at_least_two_int(value: str) -> int:
    parsed = int(value)
    if parsed < 2:
        raise argparse.ArgumentTypeError("value must be at least 2")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be a nonnegative integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("value must be nonnegative and finite")
    return parsed


def task_id_value(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise argparse.ArgumentTypeError(
            "task ID must start with a letter or digit and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )
    return value


def input_impedance_value(value: str) -> str:
    normalized = value.upper().replace(" ", "")
    aliases = {"AUTO": "AUTO", "10M": "10M", "10MOHM": "10M"}
    if normalized not in aliases:
        raise argparse.ArgumentTypeError("input impedance must be AUTO or 10M")
    return aliases[normalized]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Configure one USB Keithley DMM7510, acquire independent DCV "
            "readings, and write verified, numbered float64 TDMS records."
        )
    )
    parser.add_argument("--task-id", type=task_id_value, default=DEFAULT_TASK_ID)
    parser.add_argument("--runs", type=positive_int, default=1)
    parser.add_argument("--readings", type=at_least_two_int, default=100)
    parser.add_argument(
        "--resource",
        default=None,
        help="VISA resource; default auto-selects exactly one USB DMM7510",
    )
    parser.add_argument(
        "--terminals", choices=("FRONT", "REAR"), default="FRONT"
    )
    parser.add_argument("--range", dest="range_v", type=positive_float, default=0.1)
    parser.add_argument(
        "--input-impedance", type=input_impedance_value, default="AUTO"
    )
    parser.add_argument("--nplc", type=positive_float, default=10.0)
    parser.add_argument("--settling-delay", type=nonnegative_float, default=2.0)
    parser.add_argument("--discard-readings", type=nonnegative_int, default=3)
    parser.add_argument(
        "--inter-reading-delay", type=nonnegative_float, default=0.0
    )
    parser.add_argument("--gain", type=positive_float, default=1001.0)
    parser.add_argument("--timeout", type=positive_float, default=60.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_dir / "data",
        help="Base data directory; a task-ID subdirectory is created",
    )
    return parser.parse_args(argv)


def check_runtime() -> None:
    installed = version("nptdms")
    if installed != NPTDMS_VERSION:
        raise RuntimeError(
            f"nptdms=={NPTDMS_VERSION} is required; found {installed}. "
            f"Run: {sys.executable} -m pip install nptdms=={NPTDMS_VERSION}"
        )


def existing_run_numbers(task_dir: Path, task_id: str) -> list[int]:
    pattern = re.compile(
        rf"^{re.escape(task_id)}_dcv_(\d+)\.(?:partial\.)?tdms$",
        re.IGNORECASE,
    )
    numbers: list[int] = []
    for path in task_dir.glob(f"{task_id}_dcv_*.tdms"):
        match = pattern.fullmatch(path.name)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def next_run_number(task_dir: Path, task_id: str) -> int:
    return max(existing_run_numbers(task_dir, task_id), default=0) + 1


def select_resource(resource_manager: pyvisa.ResourceManager, configured: str | None) -> str:
    if configured:
        return configured
    candidates = [
        name
        for name in resource_manager.list_resources("?*")
        if name.upper().startswith("USB")
        and "0X05E6" in name.upper()
        and "0X7510" in name.upper()
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one USB DMM7510, found {len(candidates)}: "
            f"{candidates}. Connect one DMM7510 or specify --resource."
        )
    return candidates[0]


def normalize_terminals(response: str) -> str:
    normalized = response.strip().strip('"').upper()
    if normalized.startswith("FRON"):
        return "FRONT"
    if normalized.startswith("REAR"):
        return "REAR"
    raise RuntimeError(f"Unexpected terminal response: {response!r}")


def normalize_function(response: str) -> str:
    return response.strip().strip('"').upper()


def response_is_on(response: str) -> bool:
    normalized = response.strip().strip('"').upper()
    if normalized in {"1", "ON"}:
        return True
    if normalized in {"0", "OFF"}:
        return False
    raise RuntimeError(f"Unexpected ON/OFF response: {response!r}")


def require_close(actual: float, requested: float, description: str) -> None:
    if not np.isclose(actual, requested, rtol=1e-9, atol=1e-12):
        raise RuntimeError(
            f"Actual {description} is {actual!r}, not requested {requested!r}."
        )


def require_no_scpi_error(instrument: object, context: str) -> None:
    errors: list[str] = []
    for _ in range(20):
        response = instrument.query(":SYSTem:ERRor?").strip()
        if response.lstrip().startswith("0,"):
            break
        errors.append(response)
    else:
        errors.append("error queue did not clear after 20 entries")
    if errors:
        raise RuntimeError(f"DMM SCPI error after {context}: {'; '.join(errors)}")


def configure_and_verify(instrument: object, args: argparse.Namespace) -> dict[str, object]:
    instrument.write("*CLS")
    commands = [
        ':SENSe:FUNCtion "VOLTage:DC"',
        ":SENSe:VOLTage:RANGe:AUTO OFF",
        f":SENSe:VOLTage:RANGe {args.range_v:.17g}",
        f":SENSe:VOLTage:INPutimpedance {args.input_impedance}",
        f":SENSe:VOLTage:NPLCycles {args.nplc:.17g}",
        ":SENSe:VOLTage:AZERo ON",
        ":SENSe:VOLTage:AVERage OFF",
        ":SENSe:VOLTage:RELative:STATe OFF",
        ":SENSe:VOLTage:LINE:SYNC ON",
    ]
    for command in commands:
        instrument.write(command)
    instrument.query("*OPC?")

    actual = {
        "terminals": normalize_terminals(instrument.query(":ROUTe:TERMinals?")),
        "function": normalize_function(instrument.query(":SENSe:FUNCtion?")),
        "autorange": response_is_on(
            instrument.query(":SENSe:VOLTage:RANGe:AUTO?")
        ),
        "range_v": float(instrument.query(":SENSe:VOLTage:RANGe?")),
        "input_impedance": instrument.query(
            ":SENSe:VOLTage:INPutimpedance?"
        ).strip().strip('"').upper(),
        "nplc": float(instrument.query(":SENSe:VOLTage:NPLCycles?")),
        "autozero": response_is_on(
            instrument.query(":SENSe:VOLTage:AZERo?")
        ),
        "averaging": response_is_on(
            instrument.query(":SENSe:VOLTage:AVERage?")
        ),
        "relative": response_is_on(
            instrument.query(":SENSe:VOLTage:RELative:STATe?")
        ),
        "line_sync": response_is_on(
            instrument.query(":SENSe:VOLTage:LINE:SYNC?")
        ),
        "line_frequency_hz": float(
            instrument.query(":SYSTem:LFRequency?")
        ),
    }
    require_no_scpi_error(instrument, "configuration")

    if actual["terminals"] != args.terminals:
        raise RuntimeError(
            f"Actual terminals are {actual['terminals']}, not {args.terminals}. "
            "Use the DMM7510 front-panel TERMINALS control to select the "
            "requested input; this model exposes terminal selection as a "
            "query-only SCPI setting."
        )
    if actual["function"] != "VOLT:DC":
        raise RuntimeError(f"Actual function is {actual['function']!r}, not VOLT:DC.")
    if actual["autorange"]:
        raise RuntimeError("DCV autorange did not disable.")
    require_close(float(actual["range_v"]), args.range_v, "DCV range")
    if actual["input_impedance"] != args.input_impedance:
        raise RuntimeError(
            "Actual input impedance mode is "
            f"{actual['input_impedance']}, not {args.input_impedance}."
        )
    require_close(float(actual["nplc"]), args.nplc, "NPLC")
    if not actual["autozero"]:
        raise RuntimeError("Auto Zero did not enable.")
    if actual["averaging"]:
        raise RuntimeError("The DMM internal averaging filter did not disable.")
    if actual["relative"]:
        raise RuntimeError("REL/null did not disable.")
    if not actual["line_sync"]:
        raise RuntimeError("Line synchronization did not enable.")
    require_close(float(actual["line_frequency_hz"]), 50.0, "line frequency")
    return actual


def parse_identity(identity: str) -> dict[str, str]:
    fields = [field.strip() for field in identity.split(",")]
    fields.extend([""] * (4 - len(fields)))
    manufacturer, model, serial_number, firmware = fields[:4]
    if "KEITHLEY" not in manufacturer.upper() or "DMM7510" not in model.upper():
        raise RuntimeError(f"Expected a Keithley DMM7510; received *IDN? {identity!r}.")
    return {
        "instrument_manufacturer": manufacturer,
        "instrument_model": model,
        "instrument_serial_number": serial_number,
        "instrument_firmware_revision": firmware,
        "instrument_idn": identity,
    }


def acquire_run(
    instrument: object,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, datetime, float]:
    print(f"Waiting {args.settling_delay:g} s for the DMM input path to settle...")
    time.sleep(args.settling_delay)
    for index in range(args.discard_readings):
        discarded_v = float(instrument.query(":READ?"))
        print(
            f"  Discarded settling reading {index + 1}/{args.discard_readings}: "
            f"{discarded_v * 1e3:+.9f} mV",
            flush=True,
        )

    readings_v = np.empty(args.readings, dtype=np.float64)
    elapsed_s = np.empty(args.readings, dtype=np.float64)
    acquisition_start_utc = datetime.now(timezone.utc)
    acquisition_start = time.monotonic()

    for index in range(args.readings):
        query_start = time.monotonic()
        readings_v[index] = float(instrument.query(":READ?"))
        query_end = time.monotonic()
        if (
            not np.isfinite(readings_v[index])
            or abs(readings_v[index]) > 1.2 * args.range_v
        ):
            raise RuntimeError(
                f"Reading {index + 1} is invalid or overrange: "
                f"{readings_v[index]!r} V on the {args.range_v:g} V range."
            )
        elapsed_s[index] = 0.5 * (query_start + query_end) - acquisition_start
        running_mean_v = float(np.mean(readings_v[: index + 1]))
        elapsed = query_end - acquisition_start
        eta_s = elapsed / (index + 1) * (args.readings - index - 1)
        print(
            f"[{index + 1:03d}/{args.readings:03d}] "
            f"output={readings_v[index] * 1e3:+.9f} mV, "
            f"input={readings_v[index] / args.gain * 1e6:+.9f} uV, "
            f"running mean={running_mean_v / args.gain * 1e6:+.9f} uV, "
            f"ETA={eta_s:.1f} s",
            flush=True,
        )
        if args.inter_reading_delay > 0.0:
            time.sleep(args.inter_reading_delay)

    acquisition_duration_s = time.monotonic() - acquisition_start
    if not np.all(np.isfinite(readings_v)):
        raise RuntimeError("DMM returned NaN or infinite readings.")
    if not np.all(np.isfinite(elapsed_s)) or not np.all(np.diff(elapsed_s) > 0.0):
        raise RuntimeError("Reading timestamps are not finite and strictly increasing.")
    require_no_scpi_error(instrument, "acquisition")
    return readings_v, elapsed_s, acquisition_start_utc, acquisition_duration_s


def write_verified_tdms(
    *,
    partial_path: Path,
    final_path: Path,
    readings_v: np.ndarray,
    elapsed_s: np.ndarray,
    acquisition_start_utc: datetime,
    acquisition_duration_s: float,
    args: argparse.Namespace,
    run_number: int,
    resource_name: str,
    identity: dict[str, str],
    actual: dict[str, object],
    visa_backend: str,
) -> tuple[float, float, float]:
    if partial_path.exists() or final_path.exists():
        raise FileExistsError(f"Refusing to overwrite {partial_path} or {final_path}.")
    if readings_v.dtype != np.dtype(np.float64) or elapsed_s.dtype != np.dtype(np.float64):
        raise RuntimeError("TDMS input channels must both be float64.")
    if readings_v.size != args.readings or elapsed_s.size != args.readings:
        raise RuntimeError("TDMS input channels do not have the requested reading count.")

    mean_v = float(np.mean(readings_v))
    sample_std_v = float(np.std(readings_v, ddof=1)) if readings_v.size > 1 else 0.0
    standard_error_v = sample_std_v / np.sqrt(readings_v.size)
    root_properties = {
        "format_version": FORMAT_VERSION,
        "measurement_type": "dcv_offset",
        "task_id": args.task_id,
        "run_number": run_number,
        "test_target": "DUT RevB (with PMU)",
        "closed_loop_gain_v_per_v": args.gain,
        "resource_name": resource_name,
        "visa_backend": visa_backend,
        "pyvisa_version": version("pyvisa"),
        "nptdms_version": version("nptdms"),
        "tdms_group_name": TDMS_GROUP_NAME,
        "dcv_channel_name": DCV_CHANNEL_NAME,
        "elapsed_time_channel_name": TIME_CHANNEL_NAME,
        "acquisition_start_utc": acquisition_start_utc.replace(tzinfo=None),
        "acquisition_duration_s": acquisition_duration_s,
        "reading_count": args.readings,
        "discarded_reading_count": args.discard_readings,
        "settling_delay_s": args.settling_delay,
        "inter_reading_delay_s": args.inter_reading_delay,
        "terminals": str(actual["terminals"]),
        "measurement_function": str(actual["function"]),
        "actual_range_v": float(actual["range_v"]),
        "autorange_enabled": bool(actual["autorange"]),
        "actual_input_impedance_mode": str(actual["input_impedance"]),
        "actual_nplc": float(actual["nplc"]),
        "autozero_enabled": bool(actual["autozero"]),
        "dmm_averaging_enabled": bool(actual["averaging"]),
        "relative_enabled": bool(actual["relative"]),
        "line_sync_enabled": bool(actual["line_sync"]),
        "line_frequency_hz": float(actual["line_frequency_hz"]),
        **identity,
    }
    dcv_properties = {
        "unit_string": "V",
        "description": "Independent DMM7510 DC voltage readings",
        "dtype": str(readings_v.dtype),
        "mean_v": mean_v,
        "sample_std_v": sample_std_v,
        "standard_error_v": standard_error_v,
        "equivalent_input_offset_v": mean_v / args.gain,
    }
    time_properties = {
        "unit_string": "s",
        "description": "Midpoint time of each VISA READ query relative to acquisition start",
        "dtype": str(elapsed_s.dtype),
    }

    with TdmsWriter(partial_path, index_file=False) as writer:
        writer.write_segment(
            [
                RootObject(properties=root_properties),
                GroupObject(
                    TDMS_GROUP_NAME,
                    properties={"description": "DMM7510 amplified DUT offset measurement"},
                ),
                ChannelObject(
                    TDMS_GROUP_NAME,
                    DCV_CHANNEL_NAME,
                    readings_v,
                    properties=dcv_properties,
                ),
                ChannelObject(
                    TDMS_GROUP_NAME,
                    TIME_CHANNEL_NAME,
                    elapsed_s,
                    properties=time_properties,
                ),
            ]
        )

    verification = TdmsFile.read(partial_path)
    if str(verification.properties.get("task_id")) != args.task_id:
        raise RuntimeError("TDMS task-ID verification failed.")
    if int(verification.properties.get("run_number", -1)) != run_number:
        raise RuntimeError("TDMS run-number verification failed.")
    stored_dcv = verification[TDMS_GROUP_NAME][DCV_CHANNEL_NAME][:]
    stored_time = verification[TDMS_GROUP_NAME][TIME_CHANNEL_NAME][:]
    for channel_name, stored, original in (
        (DCV_CHANNEL_NAME, stored_dcv, readings_v),
        (TIME_CHANNEL_NAME, stored_time, elapsed_s),
    ):
        if stored.dtype != np.dtype(np.float64):
            raise RuntimeError(
                f"TDMS {channel_name} dtype verification failed: {stored.dtype}."
            )
        if stored.size != args.readings:
            raise RuntimeError(
                f"TDMS {channel_name} count verification failed: {stored.size}."
            )
        if not np.array_equal(stored, original):
            raise RuntimeError(f"TDMS {channel_name} round-trip comparison failed.")

    partial_path.replace(final_path)
    return mean_v, sample_std_v, standard_error_v


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    check_runtime()
    output_base = args.output_dir.expanduser().resolve()
    task_dir = output_base / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    resource_manager = pyvisa.ResourceManager()
    instrument = None
    try:
        resource_name = select_resource(resource_manager, args.resource)
        print(f"VISA backend: {resource_manager}")
        print(f"Opening {resource_name} with an exclusive lock...")
        try:
            instrument = resource_manager.open_resource(
                resource_name,
                access_mode=AccessModes.exclusive_lock,
                open_timeout=int(args.timeout * 1000),
            )
        except VisaIOError as exc:
            raise RuntimeError(
                f"Cannot exclusively open {resource_name}. Close the DMM Notebook, "
                "InstrumentStudio, KickStart, or other VISA clients and retry."
            ) from exc
        instrument.timeout = int(args.timeout * 1000)
        instrument.read_termination = "\n"
        instrument.write_termination = "\n"

        identity_text = instrument.query("*IDN?").strip()
        identity = parse_identity(identity_text)
        print(f"Connected: {identity_text}")
        actual = configure_and_verify(instrument, args)
        print(
            "Verified configuration: "
            f"{actual['terminals']} terminals, {float(actual['range_v']):g} V range, "
            f"input impedance {actual['input_impedance']}, "
            f"{float(actual['nplc']):g} NPLC, Auto Zero ON, DMM averaging OFF, "
            "REL OFF, line sync ON, "
            f"{float(actual['line_frequency_hz']):g} Hz line frequency"
        )
        print(f"Task: {args.task_id}")
        print(f"Output: {task_dir}")
        print(
            f"Runs requested: {args.runs}; readings per run: {args.readings}; "
            f"first run number: {next_run_number(task_dir, args.task_id):04d}"
        )

        batch_started = time.monotonic()
        for completed in range(args.runs):
            run_number = next_run_number(task_dir, args.task_id)
            stem = f"{args.task_id}_dcv_{run_number:04d}"
            final_path = task_dir / f"{stem}.tdms"
            partial_path = task_dir / f"{stem}.partial.tdms"
            print(
                f"\nRun {completed + 1}/{args.runs} (file number {run_number:04d})",
                flush=True,
            )
            run_started = time.monotonic()
            readings_v, elapsed_s, acquisition_start_utc, duration_s = acquire_run(
                instrument, args
            )
            mean_v, std_v, sem_v = write_verified_tdms(
                partial_path=partial_path,
                final_path=final_path,
                readings_v=readings_v,
                elapsed_s=elapsed_s,
                acquisition_start_utc=acquisition_start_utc,
                acquisition_duration_s=duration_s,
                args=args,
                run_number=run_number,
                resource_name=resource_name,
                identity=identity,
                actual=actual,
                visa_backend=str(resource_manager),
            )
            print(
                f"Saved {final_path.name} | output mean={mean_v * 1e3:+.9f} mV, "
                f"std={std_v * 1e6:.6f} uV, SEM={sem_v * 1e6:.6f} uV, "
                f"equivalent input offset={mean_v / args.gain * 1e6:+.9f} uV | "
                f"run time={time.monotonic() - run_started:.1f} s",
                flush=True,
            )

        print(
            f"Completed {args.runs} run(s) in "
            f"{time.monotonic() - batch_started:.1f} s."
        )
        return 0
    finally:
        if instrument is not None:
            instrument.close()
        resource_manager.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAcquisition interrupted; existing verified TDMS files remain valid.")
        raise SystemExit(130)
    except (RuntimeError, ValueError, VisaIOError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
