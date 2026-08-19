function [averageAsdVrtHz, frequencyHz, outputPaths] = ...
        runPxi5922NoiseAnalysis(dataDir, outputDir, fileStem, testLabel)
%RUNPXI5922NOISEANALYSIS Average ten PXI-5922 noise spectra.
%   [ASD, F, PATHS] = RUNPXI5922NOISEANALYSIS() reads acquisitions (1)
%   through (10) from the 2026-08-19 Unicorn COB RevA AC-coupled capture.
%   It uses the first 900,000 samples of every acquisition and calculates
%   one periodic-Hann PSD per file at 50 kS/s. The ten PSDs are averaged
%   before taking the square root to obtain the final ASD.
%
%   No per-acquisition figures are created. The function creates one final
%   log-log ASD figure and writes PNG, FIG, CSV, and MAT results below
%   results/.
%
%   Optional DATA_DIR, OUTPUT_DIR, FILE_STEM, and TEST_LABEL arguments
%   override the AC-coupled repository defaults. Every input file must
%   contain at least 900,000 finite samples.

arguments
    dataDir (1, 1) string = defaultDataDir()
    outputDir (1, 1) string = defaultOutputDir()
    fileStem (1, 1) string = ...
        "Capture_50kS_ 2026-08-19_Unicorn_COB_RevA"
    testLabel (1, 1) string = "AC coupling"
end

sampleRateHz = 50e3;
pointCount = 900000;
runCount = 10;

sourceDir = fullfile(repoRoot(), "matlab", "src");
pathCleanup = addSourcePathWhenMissing(sourceDir); %#ok<NASGU>
inputPaths = strings(runCount, 1);

% Validate the complete ten-file set before spending time on FFTs or
% writing outputs. A partial average must not be labelled as ten-run data.
for runIndex = 1:runCount
    inputPaths(runIndex) = resolveWaveformPath( ...
        dataDir, fileStem, runIndex);
    validateCaptureHeader( ...
        inputPaths(runIndex), sampleRateHz, pointCount, runIndex);
end

oneSidedPointCount = floor(pointCount/2) + 1;
perRunPsdV2PerHz = zeros(oneSidedPointCount, runCount);
frequencyHz = zeros(oneSidedPointCount, 1);

for runIndex = 1:runCount
    fprintf("Analyzing PXI-5922 acquisition %d/%d: %s\n", ...
        runIndex, runCount, inputPaths(runIndex));
    voltageV = readFirstSamples(inputPaths(runIndex), pointCount, runIndex);
    [runPsdV2PerHz, runFrequencyHz] = noiseSpectrum( ...
        voltageV, sampleRateHz, pointCount, false);

    if runIndex == 1
        frequencyHz = runFrequencyHz;
    elseif ~isequal(runFrequencyHz, frequencyHz)
        error("pxi5922:FrequencyAxisMismatch", ...
            "Acquisition %d produced an inconsistent frequency axis.", ...
            runIndex);
    end
    perRunPsdV2PerHz(:, runIndex) = runPsdV2PerHz;
end

averagePsdV2PerHz = mean(perRunPsdV2PerHz, 2);
averageAsdVrtHz = sqrt(max(averagePsdV2PerHz, 0));

if ~isfolder(outputDir)
    mkdir(outputDir);
end
outputPaths = buildOutputPaths(outputDir);

resultTable = table( ...
    frequencyHz, averageAsdVrtHz, ...
    VariableNames=["Frequency_Hz", "Average_ASD_V_per_sqrtHz"]);
writetable(resultTable, outputPaths.csvPath);

save(outputPaths.matPath, ...
    "frequencyHz", "averageAsdVrtHz", "averagePsdV2PerHz", ...
    "perRunPsdV2PerHz", "sampleRateHz", "pointCount", ...
    "runCount", "inputPaths", "fileStem", "testLabel");

figureHandle = plotAverageAsd( ...
    frequencyHz, averageAsdVrtHz, pointCount, runCount, testLabel);
savefig(figureHandle, outputPaths.figPath);
exportgraphics(figureHandle, outputPaths.figurePath, Resolution=300);

fprintf("Average ASD CSV: %s\n", outputPaths.csvPath);
fprintf("Analysis MAT: %s\n", outputPaths.matPath);
fprintf("Final ASD PNG: %s\n", outputPaths.figurePath);
fprintf("Final ASD MATLAB figure: %s\n", outputPaths.figPath);
end

function csvPath = resolveWaveformPath(dataDir, fileStem, runIndex)
numberedPath = fullfile(dataDir, sprintf( ...
    "%s (%d) Oscilloscope - Waveform Data.csv", fileStem, runIndex));
if isfile(numberedPath) || runIndex ~= 1
    csvPath = numberedPath;
    return
end

% InstrumentStudio sometimes exports the first acquisition without a
% numeric suffix, followed by (2) through (10).
unnumberedPath = fullfile(dataDir, ...
    fileStem + " Oscilloscope - Waveform Data.csv");
if isfile(unnumberedPath)
    csvPath = unnumberedPath;
else
    csvPath = numberedPath;
end
end

function validateCaptureHeader(csvPath, expectedRateHz, pointCount, runIndex)
if ~isfile(csvPath)
    error("pxi5922:MissingWaveformFile", ...
        "Acquisition %d waveform file does not exist: %s", ...
        runIndex, csvPath);
end

[sampleIntervalS, declaredPointCount] = readCaptureMetadata(csvPath);
if declaredPointCount < pointCount
    error("pxi5922:InsufficientSamples", ...
        "Acquisition %d declares only %d samples; %d are required. " + ...
        "Re-export or repeat this acquisition: %s", ...
        runIndex, declaredPointCount, pointCount, csvPath);
end
if ~(isfinite(sampleIntervalS) && sampleIntervalS > 0)
    error("pxi5922:InvalidSampleInterval", ...
        "Acquisition %d has an invalid sample interval in %s. " + ...
        "Re-export or repeat this acquisition.", runIndex, csvPath);
end
actualRateHz = 1/sampleIntervalS;
if abs(actualRateHz-expectedRateHz)/expectedRateHz > 1e-9
    error("pxi5922:UnexpectedSampleRate", ...
        "Acquisition %d uses %.9g S/s instead of %.9g S/s: %s", ...
        runIndex, actualRateHz, expectedRateHz, csvPath);
end
end

function [sampleIntervalS, declaredPointCount] = readCaptureMetadata(csvPath)
fileId = fopen(csvPath, "r");
if fileId < 0
    error("pxi5922:CannotOpenWaveformFile", ...
        "Cannot open waveform file: %s", csvPath);
end
cleanup = onCleanup(@() fclose(fileId));

sectionLine = string(fgetl(fileId));
headerLine = string(fgetl(fileId));
metadataLine = string(fgetl(fileId));
% InstrumentStudio exports UTF-8 with a BOM. ENDSWITH accepts the decoded
% BOM as well as systems that expose its three bytes as visible characters.
if ~endsWith(strtrim(sectionLine), "Meta data", IgnoreCase=true) || ...
        ~startsWith(strtrim(headerLine), "Physical channel,", ...
        IgnoreCase=true)
    error("pxi5922:InvalidWaveformHeader", ...
        "Unexpected PXI-5922 waveform header: %s", csvPath);
end

fields = split(metadataLine, ",");
if numel(fields) < 4
    error("pxi5922:InvalidWaveformHeader", ...
        "Incomplete PXI-5922 waveform metadata: %s", csvPath);
end
sampleIntervalS = str2double(strtrim(fields(3)));
declaredPointCount = str2double(strtrim(fields(4)));
if ~(isfinite(declaredPointCount) && declaredPointCount >= 0 && ...
        declaredPointCount == floor(declaredPointCount))
    error("pxi5922:InvalidSampleCount", ...
        "Invalid declared sample count in: %s", csvPath);
end
end

function voltageV = readFirstSamples(csvPath, pointCount, runIndex)
rawData = readmatrix(csvPath, NumHeaderLines=6, OutputType="double");
if isempty(rawData) || size(rawData, 2) ~= 1
    error("pxi5922:InvalidWaveformData", ...
        "Acquisition %d must contain exactly one waveform column: %s", ...
        runIndex, csvPath);
end
if size(rawData, 1) < pointCount
    error("pxi5922:InsufficientSamples", ...
        "Acquisition %d contains only %d readable samples; %d are " + ...
        "required: %s", ...
        runIndex, size(rawData, 1), pointCount, csvPath);
end

voltageV = rawData(1:pointCount, 1);
if any(~isfinite(voltageV))
    error("pxi5922:NonfiniteSamples", ...
        "Acquisition %d contains nonfinite values in its first %d samples: %s", ...
        runIndex, pointCount, csvPath);
end
end

function figureHandle = plotAverageAsd( ...
        frequencyHz, averageAsdVrtHz, pointCount, runCount, testLabel)
use = frequencyHz > 0 & isfinite(averageAsdVrtHz) & ...
    averageAsdVrtHz > 0;
if ~any(use)
    error("pxi5922:NoPlottableAsd", ...
        "The average ASD has no finite positive-frequency values.");
end

figureHandle = figure( ...
    Name="PXI-5922 average noise ASD - " + testLabel, Color="w");
loglog(frequencyHz(use), averageAsdVrtHz(use), LineWidth=1.1);
grid on;
grid minor;
xlabel("Frequency (Hz)");
ylabel("ASD (V/sqrt(Hz))");
title({ ...
    "PXI-5922 average noise ASD"; ...
    sprintf("%s (%d acquisitions, first %d points)", ...
    testLabel, runCount, pointCount)});
xlim([frequencyHz(find(use, 1, "first")), frequencyHz(end)]);
end

function outputPaths = buildOutputPaths(outputDir)
outputPaths = struct;
outputPaths.csvPath = fullfile(outputDir, "average_noise_asd.csv");
outputPaths.matPath = fullfile(outputDir, "average_noise_asd.mat");
outputPaths.figurePath = fullfile(outputDir, "average_noise_asd.png");
outputPaths.figPath = fullfile(outputDir, "average_noise_asd.fig");
end

function cleanup = addSourcePathWhenMissing(sourceDir)
pathText = [pathsep, path, pathsep];
sourceEntry = [pathsep, char(sourceDir), pathsep];
if contains(pathText, sourceEntry, "IgnoreCase", ispc)
    cleanup = onCleanup(@() []);
else
    addpath(sourceDir);
    cleanup = onCleanup(@() rmpath(sourceDir));
end
end

function path = defaultDataDir()
path = string(fullfile(repoRoot(), "data", "raw", "PXI-5922", ...
    "Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_01"));
end

function path = defaultOutputDir()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_01"));
end

function path = repoRoot()
path = fileparts(fileparts(fileparts(mfilename("fullpath"))));
end
