function [averageAsdVrtHz, frequencyHz, outputPaths] = ...
        runPxi5922FloatingInputNoiseAnalysis(dataDir, outputDir)
%RUNPXI5922FLOATINGINPUTNOISEANALYSIS Analyze the PXI-5922 noise floor.
%   [ASD, F, PATHS] = RUNPXI5922FLOATINGINPUTNOISEANALYSIS() analyzes ten
%   DC-coupled, 1 Mohm, floating-input PXI-5922 captures. No DUT or 1001x
%   gain stage is present. The function uses the same 50 kS/s,
%   first-900,000-point, ten-PSD-average method as the DUT measurements.
%
%   CSV, MAT, PNG, and MATLAB FIG outputs are written below the run_03
%   results directory. Optional DATA_DIR and OUTPUT_DIR arguments override
%   the repository defaults.

arguments
    dataDir (1, 1) string = defaultFloatingDataDir()
    outputDir (1, 1) string = defaultFloatingOutputDir()
end

fileStem = ...
    "Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_floatingInput";
[averageAsdVrtHz, frequencyHz, outputPaths] = ...
    runPxi5922NoiseAnalysis( ...
    dataDir, outputDir, fileStem, ...
    "DC-coupled floating-input noise floor");
end

function path = defaultFloatingDataDir()
path = string(fullfile(repoRoot(), "data", "raw", "PXI-5922", ...
    "Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_03"));
end

function path = defaultFloatingOutputDir()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_03"));
end

function path = repoRoot()
path = fileparts(fileparts(fileparts(mfilename("fullpath"))));
end
