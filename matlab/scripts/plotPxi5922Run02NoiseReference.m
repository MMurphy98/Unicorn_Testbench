function [figureHandle, outputPaths, result] = ...
        plotPxi5922Run02NoiseReference(matPath, outputDir)
%PLOTPXI5922RUN02NOISEREFERENCE Plot run02 against a 5.1 nV/sqrt(Hz) reference.
%   [FIG, PATHS, RESULT] = PLOTPXI5922RUN02NOISEREFERENCE() loads the saved
%   run02 average_noise_asd.mat file without processing the raw waveforms.
%   It converts the 1001x output-referred ASD to input-referred nV/sqrt(Hz),
%   plots 1 Hz through 25 kHz on log-log axes, and adds the broadband-noise
%   reference obtained from the 100 Hz through 10 kHz evaluation.

arguments
    matPath (1, 1) string {mustBeFile} = defaultMatPath()
    outputDir (1, 1) string = defaultOutputDir()
end

saved = load(matPath, "frequencyHz", "averageAsdVrtHz", ...
    "sampleRateHz", "pointCount", "runCount");
requiredFields = ["frequencyHz", "averageAsdVrtHz"];
missingFields = requiredFields(~isfield(saved, requiredFields));
if ~isempty(missingFields)
    error("pxi5922:MissingSavedResultFields", ...
        "Saved run02 result is missing: %s", strjoin(missingFields, ", "));
end

frequencyHz = double(saved.frequencyHz(:));
outputAsdVrtHz = double(saved.averageAsdVrtHz(:));
if numel(frequencyHz) ~= numel(outputAsdVrtHz)
    error("pxi5922:SavedResultSizeMismatch", ...
        "Saved run02 frequency and ASD arrays must have the same length.");
end

voltageGain = 1001;
voltsToNanovolts = 1e9;
referenceNvRtHz = 5.1;
xLimitsHz = [1, 25e3];
inputAsdNvRtHz = outputAsdVrtHz/voltageGain*voltsToNanovolts;
use = frequencyHz >= xLimitsHz(1) & frequencyHz <= xLimitsHz(2) & ...
    isfinite(inputAsdNvRtHz) & inputAsdNvRtHz > 0;
if ~any(use)
    error("pxi5922:NoPlottableRun02Data", ...
        "Saved run02 result contains no positive ASD data from 1 Hz to 25 kHz.");
end

figureHandle = figure( ...
    Name="PXI-5922 run02 input-referred noise", Color="w");
loglog(frequencyHz(use), inputAsdNvRtHz(use), ...
    LineWidth=1.0);
hold on;
referenceLine = yline(referenceNvRtHz, "--", ...
    "5.1 nV/sqrt(Hz)", LineWidth=1.5, ...
    Color=[0.85, 0.325, 0.098]);
referenceLine.LabelHorizontalAlignment = "right";
referenceLine.LabelVerticalAlignment = "bottom";
hold off;
grid on;
grid minor;
box on;
xlabel("Frequency (Hz)");
ylabel("Input-referred noise (nV/sqrt(Hz))");
title({ ...
    "Unicorn COB RevA DUT run02 input-referred noise"; ...
    "PXI-5922, 1001x gain, DC coupling, 10-capture PSD average"});
xlim(xLimitsHz);

if ~isfolder(outputDir)
    mkdir(outputDir);
end
outputPaths = struct;
outputPaths.figurePath = fullfile( ...
    outputDir, "run02_input_referred_noise_1Hz_25kHz.png");
outputPaths.figPath = fullfile( ...
    outputDir, "run02_input_referred_noise_1Hz_25kHz.fig");
savefig(figureHandle, outputPaths.figPath);
exportgraphics(figureHandle, outputPaths.figurePath, Resolution=300);

result = struct;
result.frequencyHz = frequencyHz(use);
result.inputAsdNvRtHz = inputAsdNvRtHz(use);
result.referenceNvRtHz = referenceNvRtHz;
result.xLimitsHz = xLimitsHz;
result.voltageGain = voltageGain;
result.matPath = matPath;

fprintf("Loaded saved run02 result: %s\n", matPath);
fprintf("Run02 input-referred PNG: %s\n", outputPaths.figurePath);
fprintf("Run02 input-referred MATLAB figure: %s\n", outputPaths.figPath);
end

function path = defaultMatPath()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_02", "average_noise_asd.mat"));
end

function path = defaultOutputDir()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_02"));
end

function path = repoRoot()
scriptDir = fileparts(mfilename("fullpath"));
path = fileparts(fileparts(scriptDir));
end
