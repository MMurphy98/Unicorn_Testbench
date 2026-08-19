function [figureHandle, outputPaths, comparison] = ...
        plotPxi5922AcDcComparison(acMatPath, dcMatPath, outputDir)
%PLOTPXI5922ACDCCOMPARISON Plot saved AC and DC average ASD together.
%   [FIG, PATHS, DATA] = PLOTPXI5922ACDCCOMPARISON() loads only the saved
%   average_noise_asd.mat files for run_01 (AC coupling) and run_02 (DC
%   coupling). It does not read waveform CSV files or recalculate spectra.
%
%   The function verifies that the saved frequency axes and acquisition
%   parameters match, divides both saved output ASDs by the 1001x voltage
%   gain, and converts V/sqrt(Hz) to nV/sqrt(Hz). It then creates one
%   log-log input-referred-noise comparison with a legend. PNG and editable
%   MATLAB FIG files are saved below results/.

arguments
    acMatPath (1, 1) string {mustBeFile} = defaultAcMatPath()
    dcMatPath (1, 1) string {mustBeFile} = defaultDcMatPath()
    outputDir (1, 1) string = defaultOutputDir()
end

ac = loadSavedAverage(acMatPath, "AC coupling (run_01)");
dc = loadSavedAverage(dcMatPath, "DC coupling (run_02)");
validateCompatibleResults(ac, dc);

frequencyHz = ac.frequencyHz;
voltageGain = 1001;
voltsToNanovolts = 1e9;
acInputNoiseNvRtHz = ac.averageAsdVrtHz/voltageGain*voltsToNanovolts;
dcInputNoiseNvRtHz = dc.averageAsdVrtHz/voltageGain*voltsToNanovolts;
use = frequencyHz > 0 & ...
    acInputNoiseNvRtHz > 0 & dcInputNoiseNvRtHz > 0;
if ~any(use)
    error("pxi5922:NoPlottableComparisonData", ...
        "The saved AC/DC ASD results have no common positive-frequency data.");
end

figureHandle = figure( ...
    Name="PXI-5922 DUT AC/DC input-referred noise", Color="w");
loglog(frequencyHz(use), acInputNoiseNvRtHz(use), LineWidth=1.1);
hold on;
loglog(frequencyHz(use), dcInputNoiseNvRtHz(use), LineWidth=1.1);
hold off;
grid on;
grid minor;
xlabel("Frequency (Hz)");
ylabel("Input-referred noise (nV/sqrt(Hz))");
title({ ...
    "Unicorn COB RevA DUT input-referred noise"; ...
    "PXI-5922, 1001x gain: AC vs DC coupling"});
legend(ac.label, dc.label, Location="best", Interpreter="none");
xlim([frequencyHz(find(use, 1, "first")), frequencyHz(end)]);

if ~isfolder(outputDir)
    mkdir(outputDir);
end
outputPaths = struct;
outputPaths.figurePath = fullfile( ...
    outputDir, "ac_dc_average_noise_asd_comparison.png");
outputPaths.figPath = fullfile( ...
    outputDir, "ac_dc_average_noise_asd_comparison.fig");
savefig(figureHandle, outputPaths.figPath);
exportgraphics(figureHandle, outputPaths.figurePath, Resolution=300);

comparison = struct;
comparison.frequencyHz = frequencyHz;
comparison.acOutputAsdVrtHz = ac.averageAsdVrtHz;
comparison.dcOutputAsdVrtHz = dc.averageAsdVrtHz;
comparison.acInputNoiseNvRtHz = acInputNoiseNvRtHz;
comparison.dcInputNoiseNvRtHz = dcInputNoiseNvRtHz;
comparison.voltageGain = voltageGain;
comparison.sampleRateHz = ac.sampleRateHz;
comparison.pointCount = ac.pointCount;
comparison.runCountPerCondition = ac.runCount;
comparison.acMatPath = acMatPath;
comparison.dcMatPath = dcMatPath;

fprintf("Loaded saved AC result: %s\n", acMatPath);
fprintf("Loaded saved DC result: %s\n", dcMatPath);
fprintf("AC/DC comparison PNG: %s\n", outputPaths.figurePath);
fprintf("AC/DC comparison MATLAB figure: %s\n", outputPaths.figPath);
end

function result = loadSavedAverage(matPath, label)
requiredNames = [ ...
    "frequencyHz"; ...
    "averageAsdVrtHz"; ...
    "sampleRateHz"; ...
    "pointCount"; ...
    "runCount"];
available = string({whos("-file", matPath).name});
missing = setdiff(requiredNames, available);
if ~isempty(missing)
    error("pxi5922:IncompleteSavedAverage", ...
        "Saved result is missing %s: %s", ...
        strjoin(missing, ", "), matPath);
end

loaded = load(matPath, requiredNames{:});
validateattributes(loaded.frequencyHz, ...
    {'double'}, {'real', 'finite', 'column', 'nonempty'});
validateattributes(loaded.averageAsdVrtHz, ...
    {'double'}, ...
    {'real', 'finite', 'nonnegative', 'column', 'nonempty'});
if ~isequal(size(loaded.frequencyHz), size(loaded.averageAsdVrtHz))
    error("pxi5922:InvalidSavedAverageSize", ...
        "Frequency and ASD sizes differ in: %s", matPath);
end
if any(diff(loaded.frequencyHz) <= 0)
    error("pxi5922:InvalidSavedFrequencyAxis", ...
        "Saved frequency axis is not strictly increasing: %s", matPath);
end

result = loaded;
result.label = label;
result.matPath = matPath;
end

function validateCompatibleResults(ac, dc)
if ~isequal(ac.frequencyHz, dc.frequencyHz)
    error("pxi5922:SavedFrequencyAxisMismatch", ...
        "Saved AC and DC frequency axes do not match.");
end
if ac.sampleRateHz ~= dc.sampleRateHz || ...
        ac.pointCount ~= dc.pointCount || ac.runCount ~= dc.runCount
    error("pxi5922:SavedAcquisitionMismatch", ...
        "Saved AC and DC acquisition parameters do not match.");
end
end

function path = defaultAcMatPath()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_01", "average_noise_asd.mat"));
end

function path = defaultDcMatPath()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_02", "average_noise_asd.mat"));
end

function path = defaultOutputDir()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_ac_dc_comparison"));
end

function path = repoRoot()
path = fileparts(fileparts(fileparts(mfilename("fullpath"))));
end
