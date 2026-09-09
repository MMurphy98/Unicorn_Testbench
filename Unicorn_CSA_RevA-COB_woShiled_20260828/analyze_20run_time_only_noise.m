%% Analyze 20 time-only InstrumentStudio TDMS noise captures
% The input files contain Channel 0 waveform data but no saved device FFT.
% This script:
%   1. calculates and preserves one correctly normalized FFT/PSD/ASD per run;
%   2. averages all runs in linear PSD units, then converts to V/sqrt(Hz);
%   3. saves full-resolution and 1/12-octave data, MATLAB .fig files, PNGs,
%      CSV summaries, and reusable MAT files under analysis_results.
%
% Requirement: MATLAB R2022a or newer with Data Acquisition Toolbox.
% Signal Processing Toolbox is not required.

% A small wrapper may define dataFolderOverride and analysisProfileOverride
% before calling this script.  This keeps multiple data sets and analysis
% profiles on the exact same reviewed implementation.
if exist("dataFolderOverride", "var")
    dataFolderOverride = string(dataFolderOverride);
else
    dataFolderOverride = "";
end
if exist("analysisProfileOverride", "var")
    analysisProfile = lower(strtrim(string(analysisProfileOverride)));
else
    analysisProfile = "whole_record_22s";
end
clearvars -except dataFolderOverride analysisProfile;
close all;
clc;

%% User settings
scriptPath = string(mfilename("fullpath"));
if strlength(dataFolderOverride) > 0
    dataFolder = dataFolderOverride;
elseif strlength(scriptPath) == 0
    dataFolder = string(pwd);
else
    dataFolder = string(fileparts(scriptPath));
end
clear dataFolderOverride;

tdmsFilePattern = "*.tdms";
expectedRunCount = 20;
channelSearchText = "Channel 0";

% Analysis profiles deliberately write to separate locations so a Welch
% rerun never overwrites the archived 22 s full-record result.
switch analysisProfile
    case {"whole_record_22s", "whole-record"}
        analysisProfile = "whole_record_22s";
        segmentationMode = "whole-record";
        segmentDurationSeconds = 8; % unused in whole-record mode
        segmentOverlapFraction = 0.5; % unused in whole-record mode
        outputRelativeFolder = "analysis_results";
    case {"welch_8s_50pct", "fixed-duration"}
        analysisProfile = "welch_8s_50pct";
        segmentationMode = "fixed-duration";
        segmentDurationSeconds = 8;
        segmentOverlapFraction = 0.5;
        outputRelativeFolder = fullfile( ...
            "analysis_results", "welch_8s_50pct");
    otherwise
        error("Unknown analysis profile '%s'. Use 'whole_record_22s' " + ...
            "or 'welch_8s_50pct'.", analysisProfile);
end

removeMeanPerSegment = true;
windowName = "Hamming";       % periodic Hamming, matching prior setup
plotFrequencyRangeHz = [1, 25e3];
fractionalOctaveBandsPerOctave = 12;

outputFolder = fullfile(dataFolder, outputRelativeFolder);
perRunFolder = fullfile(outputFolder, "per_run_fft");
pngResolution = 240;

if ~isfolder(outputFolder)
    mkdir(outputFolder);
end
if ~isfolder(perRunFolder)
    mkdir(perRunFolder);
end

%% Resolve and naturally order Run 1 ... Run 20
listing = dir(fullfile(dataFolder, tdmsFilePattern));
listing = listing(~[listing.isdir]);
assert(numel(listing) == expectedRunCount, ...
    "Expected %d TDMS files under %s, but found %d.", ...
    expectedRunCount, dataFolder, numel(listing));

[runNumbers, order] = parseAndSortRunNumbers(string({listing.name}));
listing = listing(order);
inputFilePaths = fullfile(string({listing.folder}), ...
    string({listing.name})).';
runNumbers = runNumbers(:);

%% Allocate per-run outputs while processing one TDMS at a time
runCount = numel(inputFilePaths);
psdV2PerHzByRun = [];
octavePsdV2PerHzByRun = [];
waveformSignatureByRun = nan(runCount, 8);

sourceFile = strings(runCount, 1);
sampleCountByRun = zeros(runCount, 1);
sampleRateHzByRun = zeros(runCount, 1);
startTimeSecondsByRun = zeros(runCount, 1);
meanVByRun = zeros(runCount, 1);
acRmsVByRun = zeros(runCount, 1);
segmentCountByRun = zeros(runCount, 1);
discardedSamplesByRun = zeros(runCount, 1);
asd1HzVPerSqrtHzByRun = zeros(runCount, 1);
integratedNoise1To25kVrmsByRun = zeros(runCount, 1);
asd100To1kVPerSqrtHzByRun = zeros(runCount, 1);
asd1kTo10kVPerSqrtHzByRun = zeros(runCount, 1);
asd10kTo25kVPerSqrtHzByRun = zeros(runCount, 1);
rollOff10kTo25kVs1kTo10kDbByRun = zeros(runCount, 1);
duplicateOfRun = nan(runCount, 1);

frequencyHz = [];
octaveFrequencyHz = [];
referenceSampleRateHz = nan;
referenceSampleCount = nan;
referenceFftInfo = struct;

fprintf("Processing %d TDMS captures...\n", runCount);

for runIndex = 1:runCount
    tdmsPath = inputFilePaths(runIndex);
    fprintf("  Run %02d (%d/%d): %s\n", ...
        runNumbers(runIndex), runIndex, runCount, tdmsPath);

    [voltageV, sampleRateHz, startTimeSeconds, channelName] = ...
        readChannel0Waveform(tdmsPath, channelSearchText);
    currentSampleCount = numel(voltageV);

    % Detect exact duplicates against every earlier run.  A compact
    % signature identifies candidates; candidates are then re-read and
    % compared sample-by-sample, so non-adjacent duplicates are not missed.
    currentWaveformSignature = waveformSignature(voltageV);
    if runIndex > 1
        signatureMatches = find(all( ...
            waveformSignatureByRun(1:runIndex-1, :) == ...
            currentWaveformSignature, 2));
        for candidateIndex = reshape(signatureMatches, 1, [])
            [candidateVoltageV, ~, ~, ~] = readChannel0Waveform( ...
                inputFilePaths(candidateIndex), channelSearchText);
            if isequal(voltageV, candidateVoltageV)
                duplicateOfRun(runIndex) = runNumbers(candidateIndex);
                break;
            end
        end
    end
    waveformSignatureByRun(runIndex, :) = currentWaveformSignature;

    if runIndex == 1
        referenceSampleRateHz = sampleRateHz;
        referenceSampleCount = currentSampleCount;
    else
        assert(abs(sampleRateHz-referenceSampleRateHz) <= ...
            max(1e-9*referenceSampleRateHz, 1e-9), ...
            "Run %d has sample rate %.12g Hz; expected %.12g Hz.", ...
            runNumbers(runIndex), sampleRateHz, referenceSampleRateHz);
        if strcmpi(segmentationMode, "whole-record")
            assert(currentSampleCount == referenceSampleCount, ...
                "Run %d has %d samples; expected %d for whole-record mode.", ...
                runNumbers(runIndex), currentSampleCount, ...
                referenceSampleCount);
        end
    end

    [currentFrequencyHz, currentPsdV2PerHz, currentFftInfo] = ...
        estimateSegmentedPsd(voltageV, sampleRateHz, windowName, ...
        removeMeanPerSegment, segmentationMode, ...
        segmentDurationSeconds, segmentOverlapFraction);

    if runIndex == 1
        frequencyHz = currentFrequencyHz;
        referenceFftInfo = currentFftInfo;
        psdV2PerHzByRun = zeros(numel(frequencyHz), runCount);
    else
        assertSameGrid(frequencyHz, currentFrequencyHz, ...
            "time-derived PSD", tdmsPath);
    end
    psdV2PerHzByRun(:, runIndex) = currentPsdV2PerHz; %#ok<SAGROW>

    [currentOctaveFrequencyHz, currentOctavePsdV2PerHz] = ...
        fractionalOctavePsdAverage(currentFrequencyHz, ...
        currentPsdV2PerHz, fractionalOctaveBandsPerOctave, ...
        plotFrequencyRangeHz);
    if runIndex == 1
        octaveFrequencyHz = currentOctaveFrequencyHz;
        octavePsdV2PerHzByRun = zeros( ...
            numel(octaveFrequencyHz), runCount);
    else
        assertSameGrid(octaveFrequencyHz, currentOctaveFrequencyHz, ...
            "fractional-octave PSD", tdmsPath);
    end
    octavePsdV2PerHzByRun(:, runIndex) = currentOctavePsdV2PerHz; %#ok<SAGROW>

    currentAsdVPerSqrtHz = sqrt(currentPsdV2PerHz);
    currentOctaveAsdVPerSqrtHz = sqrt(currentOctavePsdV2PerHz);
    [~, oneHzIndex] = min(abs(octaveFrequencyHz-1));

    sourceFile(runIndex) = string(listing(runIndex).name);
    sampleCountByRun(runIndex) = currentSampleCount;
    sampleRateHzByRun(runIndex) = sampleRateHz;
    startTimeSecondsByRun(runIndex) = startTimeSeconds;
    meanVByRun(runIndex) = mean(voltageV);
    acRmsVByRun(runIndex) = sqrt(mean((voltageV-mean(voltageV)).^2));
    segmentCountByRun(runIndex) = currentFftInfo.segmentCount;
    discardedSamplesByRun(runIndex) = currentFftInfo.discardedSamples;
    asd1HzVPerSqrtHzByRun(runIndex) = ...
        currentOctaveAsdVPerSqrtHz(oneHzIndex);
    integratedNoise1To25kVrmsByRun(runIndex) = ...
        integrateNoise(currentFrequencyHz, currentPsdV2PerHz, 1, 25e3);
    asd100To1kVPerSqrtHzByRun(runIndex) = ...
        bandRmsAsd(currentFrequencyHz, currentPsdV2PerHz, 100, 1e3);
    asd1kTo10kVPerSqrtHzByRun(runIndex) = ...
        bandRmsAsd(currentFrequencyHz, currentPsdV2PerHz, 1e3, 10e3);
    asd10kTo25kVPerSqrtHzByRun(runIndex) = ...
        bandRmsAsd(currentFrequencyHz, currentPsdV2PerHz, 10e3, 25e3);
    rollOff10kTo25kVs1kTo10kDbByRun(runIndex) = 20*log10( ...
        asd10kTo25kVPerSqrtHzByRun(runIndex) / ...
        asd1kTo10kVPerSqrtHzByRun(runIndex));

    runMetadata = struct;
    runMetadata.runNumber = runNumbers(runIndex);
    runMetadata.sourceFile = sourceFile(runIndex);
    runMetadata.sourcePath = tdmsPath;
    runMetadata.channelName = channelName;
    runMetadata.sampleCount = currentSampleCount;
    runMetadata.sampleRateHz = sampleRateHz;
    runMetadata.startTimeSeconds = startTimeSeconds;
    runMetadata.meanV = meanVByRun(runIndex);
    runMetadata.acRmsV = acRmsVByRun(runIndex);
    runMetadata.duplicateOfRun = duplicateOfRun(runIndex);
    runMetadata.waveformUnitAssumption = ...
        "TDMS unit metadata is blank; numeric values are interpreted as volts.";
    runMetadata.fftInfo = currentFftInfo;
    runMetadata.units.frequency = "Hz";
    runMetadata.units.psd = "V^2/Hz";
    runMetadata.units.asd = "V/sqrt(Hz)";

    psdV2PerHz = currentPsdV2PerHz;
    asdVPerSqrtHz = currentAsdVPerSqrtHz;
    octaveAsdVPerSqrtHz = currentOctaveAsdVPerSqrtHz;
    perRunPath = fullfile(perRunFolder, sprintf( ...
        "Run_%02d_FFT.mat", runNumbers(runIndex)));
    save(perRunPath, "frequencyHz", "psdV2PerHz", ...
        "asdVPerSqrtHz", "octaveFrequencyHz", ...
        "octaveAsdVPerSqrtHz", "runMetadata", "-v7.3");
end

%% Equal-run ensemble average: average PSD first, then take square root
ensemblePsdV2PerHz = mean(psdV2PerHzByRun, 2);
ensembleAsdVPerSqrtHz = sqrt(ensemblePsdV2PerHz);
ensembleOctavePsdV2PerHz = mean(octavePsdV2PerHzByRun, 2);
ensembleOctaveAsdVPerSqrtHz = sqrt(ensembleOctavePsdV2PerHz);

[~, oneHzIndex] = min(abs(octaveFrequencyHz-1));
ensembleAsd1HzVPerSqrtHz = ...
    ensembleOctaveAsdVPerSqrtHz(oneHzIndex);
ensembleIntegratedNoise1To25kVrms = ...
    integrateNoise(frequencyHz, ensemblePsdV2PerHz, 1, 25e3);

% Preserve a supplementary de-duplicated diagnostic.  The requested main
% result above remains the equal-weight average of all 20 input files.
isExactDuplicate = ~isnan(duplicateOfRun);
independentRunMask = ~isExactDuplicate;
independentRunCount = nnz(independentRunMask);
deduplicatedPsdV2PerHz = mean( ...
    psdV2PerHzByRun(:, independentRunMask), 2);
deduplicatedAsdVPerSqrtHz = sqrt(deduplicatedPsdV2PerHz);
deduplicatedOctavePsdV2PerHz = mean( ...
    octavePsdV2PerHzByRun(:, independentRunMask), 2);
deduplicatedOctaveAsdVPerSqrtHz = ...
    sqrt(deduplicatedOctavePsdV2PerHz);
deduplicatedAsd1HzVPerSqrtHz = ...
    deduplicatedOctaveAsdVPerSqrtHz(oneHzIndex);
deduplicatedDifference1HzPercent = 100*( ...
    deduplicatedAsd1HzVPerSqrtHz/ensembleAsd1HzVPerSqrtHz-1);

ensembleAsd1kTo10kVPerSqrtHz = ...
    bandRmsAsd(frequencyHz, ensemblePsdV2PerHz, 1e3, 10e3);
ensembleAsd10kTo25kVPerSqrtHz = ...
    bandRmsAsd(frequencyHz, ensemblePsdV2PerHz, 10e3, 25e3);
ensembleRollOff10kTo25kVs1kTo10kDb = 20*log10( ...
    ensembleAsd10kTo25kVPerSqrtHz/ensembleAsd1kTo10kVPerSqrtHz);
[spur50FrequencyHz, spur50AsdVPerSqrtHz] = peakAsdInBand( ...
    frequencyHz, ensembleAsdVPerSqrtHz, 49, 51);
[spur150FrequencyHz, spur150AsdVPerSqrtHz] = peakAsdInBand( ...
    frequencyHz, ensembleAsdVPerSqrtHz, 149, 151);
spur50IntegratedVrms = integrateNoise( ...
    frequencyHz, ensemblePsdV2PerHz, 49.5, 50.5);
spur150IntegratedVrms = integrateNoise( ...
    frequencyHz, ensemblePsdV2PerHz, 149.5, 150.5);

%% Per-run summary and non-destructive outlier flags
acRmsOutlier = robustOutlierFlag(acRmsVByRun);
asd1HzOutlier = robustOutlierFlag(asd1HzVPerSqrtHzByRun);
isOutlier = acRmsOutlier | asd1HzOutlier;

runSummary = table(runNumbers, sourceFile, sampleCountByRun, ...
    sampleRateHzByRun, startTimeSecondsByRun, meanVByRun, acRmsVByRun, ...
    asd1HzVPerSqrtHzByRun, integratedNoise1To25kVrmsByRun, ...
    asd100To1kVPerSqrtHzByRun, asd1kTo10kVPerSqrtHzByRun, ...
    asd10kTo25kVPerSqrtHzByRun, ...
    rollOff10kTo25kVs1kTo10kDbByRun, segmentCountByRun, ...
    discardedSamplesByRun, duplicateOfRun, isExactDuplicate, ...
    acRmsOutlier, asd1HzOutlier, isOutlier, ...
    VariableNames=["Run", "SourceFile", "Samples", "SampleRate_Hz", ...
    "StartTime_s", "Mean_V", "AC_RMS_V", "ASD_1Hz_V_rtHz", ...
    "IntegratedNoise_1_25k_Vrms", "ASD_100_1k_V_rtHz", ...
    "ASD_1k_10k_V_rtHz", "ASD_10k_25k_V_rtHz", ...
    "RollOff_10k_25k_vs_1k_10k_dB", ...
    "SegmentCount", "DiscardedSamples", "DuplicateOfRun", ...
    "IsExactDuplicate", ...
    "Outlier_AC_RMS", "Outlier_ASD_1Hz", "IsOutlier"]);

%% Save numeric results
analysisSettings = struct;
analysisSettings.dataFolder = dataFolder;
analysisSettings.analysisProfile = analysisProfile;
analysisSettings.tdmsFilePattern = tdmsFilePattern;
analysisSettings.expectedRunCount = expectedRunCount;
analysisSettings.channelSearchText = channelSearchText;
analysisSettings.segmentationMode = segmentationMode;
analysisSettings.segmentDurationSeconds = segmentDurationSeconds;
analysisSettings.segmentOverlapFraction = segmentOverlapFraction;
analysisSettings.removeMeanPerSegment = removeMeanPerSegment;
analysisSettings.windowName = windowName;
analysisSettings.waveformUnitAssumption = ...
    "TDMS channel unit metadata is blank; numeric values are interpreted as volts.";
analysisSettings.duplicatePolicy = ...
    "Exact duplicates are flagged but retained with equal weight in the requested 20-run average.";
analysisSettings.countDuplicateRunsInAverage = true;
analysisSettings.plotFrequencyRangeHz = plotFrequencyRangeHz;
analysisSettings.fractionalOctaveBandsPerOctave = ...
    fractionalOctaveBandsPerOctave;
analysisSettings.fftInfo = referenceFftInfo;
analysisSettings.units.frequency = "Hz";
analysisSettings.units.psd = "V^2/Hz";
analysisSettings.units.asd = "V/sqrt(Hz)";

analysisFindings = struct;
analysisFindings.independentRunCount = independentRunCount;
analysisFindings.deduplicatedAsd1HzVPerSqrtHz = ...
    deduplicatedAsd1HzVPerSqrtHz;
analysisFindings.deduplicatedDifference1HzPercent = ...
    deduplicatedDifference1HzPercent;
analysisFindings.ensembleAsd1kTo10kVPerSqrtHz = ...
    ensembleAsd1kTo10kVPerSqrtHz;
analysisFindings.ensembleAsd10kTo25kVPerSqrtHz = ...
    ensembleAsd10kTo25kVPerSqrtHz;
analysisFindings.ensembleRollOff10kTo25kVs1kTo10kDb = ...
    ensembleRollOff10kTo25kVs1kTo10kDb;
analysisFindings.meanPerRunRollOffDb = ...
    mean(rollOff10kTo25kVs1kTo10kDbByRun);
analysisFindings.stdPerRunRollOffDb = ...
    std(rollOff10kTo25kVs1kTo10kDbByRun);
analysisFindings.spur50FrequencyHz = spur50FrequencyHz;
analysisFindings.spur50AsdVPerSqrtHz = spur50AsdVPerSqrtHz;
analysisFindings.spur50IntegratedVrms = spur50IntegratedVrms;
analysisFindings.spur150FrequencyHz = spur150FrequencyHz;
analysisFindings.spur150AsdVPerSqrtHz = spur150AsdVPerSqrtHz;
analysisFindings.spur150IntegratedVrms = spur150IntegratedVrms;
analysisFindings.rollOffInterpretation = ...
    "The high-frequency roll-off is repeatable across runs; separating DUT response from acquisition-chain response requires reference calibration.";

save(fullfile(outputFolder, "Average_FFT.mat"), ...
    "frequencyHz", "ensemblePsdV2PerHz", ...
    "ensembleAsdVPerSqrtHz", "octaveFrequencyHz", ...
    "ensembleOctavePsdV2PerHz", "ensembleOctaveAsdVPerSqrtHz", ...
    "ensembleAsd1HzVPerSqrtHz", ...
    "ensembleIntegratedNoise1To25kVrms", ...
    "deduplicatedPsdV2PerHz", "deduplicatedAsdVPerSqrtHz", ...
    "deduplicatedOctavePsdV2PerHz", ...
    "deduplicatedOctaveAsdVPerSqrtHz", ...
    "deduplicatedAsd1HzVPerSqrtHz", "independentRunMask", ...
    "runSummary", "analysisSettings", "analysisFindings", ...
    "inputFilePaths", "-v7.3");

% This compact master file preserves every run's full-resolution PSD in
% matrix columns.  The corresponding ASD is sqrt(psdV2PerHzByRun).
save(fullfile(outputFolder, "All_20_Runs_FFT.mat"), ...
    "frequencyHz", "psdV2PerHzByRun", ...
    "octaveFrequencyHz", "octavePsdV2PerHzByRun", ...
    "runNumbers", "sourceFile", "runSummary", ...
    "analysisSettings", "analysisFindings", "inputFilePaths", "-v7.3");

writetable(runSummary, fullfile(outputFolder, "Per_Run_Summary.csv"));

averageFullResolutionTable = table(frequencyHz, ...
    ensemblePsdV2PerHz, ensembleAsdVPerSqrtHz, ...
    VariableNames=["Frequency_Hz", "Average_PSD_V2_per_Hz", ...
    "Average_ASD_V_per_rtHz"]);
writetable(averageFullResolutionTable, ...
    fullfile(outputFolder, "Average_FFT_FullResolution.csv"));

averageOctaveTable = table(octaveFrequencyHz, ...
    ensembleOctavePsdV2PerHz, ensembleOctaveAsdVPerSqrtHz, ...
    VariableNames=["Frequency_Hz", "Average_PSD_V2_per_Hz", ...
    "Average_ASD_V_per_rtHz"]);
writetable(averageOctaveTable, ...
    fullfile(outputFolder, "Average_FFT_1over12Octave.csv"));

deduplicatedOctaveTable = table(octaveFrequencyHz, ...
    deduplicatedOctavePsdV2PerHz, ...
    deduplicatedOctaveAsdVPerSqrtHz, ...
    VariableNames=["Frequency_Hz", "Deduplicated_PSD_V2_per_Hz", ...
    "Deduplicated_ASD_V_per_rtHz"]);
deduplicatedOctaveCsvName = sprintf( ...
    "Average_FFT_Deduplicated%d_1over12Octave.csv", ...
    independentRunCount);
writetable(deduplicatedOctaveTable, ...
    fullfile(outputFolder, deduplicatedOctaveCsvName));

octaveRunVariableNames = "Run_" + compose("%02d", runNumbers) + ...
    "_ASD_V_per_rtHz";
perRunOctaveTable = array2table( ...
    sqrt(octavePsdV2PerHzByRun), ...
    VariableNames=octaveRunVariableNames);
perRunOctaveTable = addvars(perRunOctaveTable, octaveFrequencyHz, ...
    Before=1, NewVariableNames="Frequency_Hz");
writetable(perRunOctaveTable, ...
    fullfile(outputFolder, "Per_Run_FFT_1over12Octave.csv"));

%% Figure 1: every run's preserved FFT plus the ensemble average
allRunsFigure = figure(Name="All 20 run FFTs", Color="w", ...
    Position=[100, 100, 1200, 760]);
axesHandle = axes(allRunsFigure);
set(axesHandle, XScale="log", YScale="log");
hold(axesHandle, "on");
runColors = turbo(runCount);
individualHandle = gobjects(1);
for runIndex = 1:runCount
    currentAsd = sqrt(octavePsdV2PerHzByRun(:, runIndex));
    if runIndex == 1
        individualHandle = loglog(axesHandle, octaveFrequencyHz, ...
            currentAsd, Color=runColors(runIndex, :), ...
            LineWidth=0.75, DisplayName="Individual runs");
    else
        loglog(axesHandle, octaveFrequencyHz, currentAsd, ...
            Color=runColors(runIndex, :), LineWidth=0.75, ...
            HandleVisibility="off");
    end
end
averageHandle = loglog(axesHandle, octaveFrequencyHz, ...
    ensembleOctaveAsdVPerSqrtHz, Color="k", LineWidth=2.4, ...
    DisplayName="20-run PSD ensemble average");
hold(axesHandle, "off");
grid(axesHandle, "on");
xlim(axesHandle, plotFrequencyRangeHz);
xlabel(axesHandle, "Frequency (Hz)");
ylabel(axesHandle, "Voltage noise density (V/\surdHz)");
title(axesHandle, ...
    "Twenty Channel 0 FFTs and equal-power ensemble average");
legend(axesHandle, [individualHandle, averageHandle], ...
    Location="best", Interpreter="none");

savefig(allRunsFigure, fullfile(outputFolder, "All_20_Runs_FFT.fig"));
exportgraphics(allRunsFigure, ...
    fullfile(outputFolder, "All_20_Runs_FFT.png"), ...
    Resolution=pngResolution);

%% Figure 2: final average FFT, full resolution and smoothed display
averageFigure = figure(Name="Final average FFT", Color="w", ...
    Position=[120, 120, 1200, 760]);
averageAxes = axes(averageFigure);
set(averageAxes, XScale="log", YScale="log");
fullUse = frequencyHz >= plotFrequencyRangeHz(1) & ...
    frequencyHz <= plotFrequencyRangeHz(2) & ...
    ensembleAsdVPerSqrtHz > 0;
if strcmpi(segmentationMode, "fixed-duration")
    loglog(averageAxes, frequencyHz(fullUse), ...
        ensembleAsdVPerSqrtHz(fullUse), ...
        Color=[0.85, 0.325, 0.098], LineWidth=1.15, ...
        DisplayName=sprintf( ...
        "20-run %.3g s Welch PSD average, %.0f%% overlap", ...
        segmentDurationSeconds, 100*segmentOverlapFraction));
    hold(averageAxes, "on");
    loglog(averageAxes, octaveFrequencyHz, ...
        ensembleOctaveAsdVPerSqrtHz, ...
        Color=[0.25, 0.25, 0.25], LineWidth=1.4, ...
        LineStyle="--", ...
        DisplayName="Optional 1/12-octave power trend");
else
    loglog(averageAxes, frequencyHz(fullUse), ...
        ensembleAsdVPerSqrtHz(fullUse), ...
        Color=[0.65, 0.80, 0.94], LineWidth=0.45, ...
        DisplayName="20-run average, full resolution");
    hold(averageAxes, "on");
    loglog(averageAxes, octaveFrequencyHz, ...
        ensembleOctaveAsdVPerSqrtHz, ...
        Color=[0.85, 0.325, 0.098], LineWidth=2.0, ...
        DisplayName="1/12-octave PSD average");
end
loglog(averageAxes, octaveFrequencyHz(oneHzIndex), ...
    ensembleOctaveAsdVPerSqrtHz(oneHzIndex), "ko", ...
    MarkerFaceColor="k", MarkerSize=6, ...
    DisplayName=sprintf("1 Hz: %.4g V/rtHz", ...
    ensembleAsd1HzVPerSqrtHz));
hold(averageAxes, "off");
grid(averageAxes, "on");
xlim(averageAxes, plotFrequencyRangeHz);
xlabel(averageAxes, "Frequency (Hz)");
ylabel(averageAxes, "Voltage noise density (V/\surdHz)");
if strcmpi(segmentationMode, "fixed-duration")
    title(averageAxes, ...
        "Final 20-run Channel 0 noise ASD - 8 s Welch, 50% overlap");
else
    title(averageAxes, "Final 20-run average Channel 0 noise FFT");
end
legend(averageAxes, Location="best", Interpreter="none");

savefig(averageFigure, fullfile(outputFolder, "Average_FFT.fig"));
exportgraphics(averageFigure, fullfile(outputFolder, "Average_FFT.png"), ...
    Resolution=pngResolution);

% The requested formal presentation range is 1 Hz to 1 kHz.  Keep this as
% a separate artifact so the full 1 Hz to 25 kHz diagnostic remains
% available without changing the stated DUT-noise reporting bandwidth.
if strcmpi(segmentationMode, "fixed-duration")
    formalFigure = figure(Name="Formal 1 Hz to 1 kHz Welch ASD", ...
        Color="w", Position=[130, 130, 1200, 760]);
    formalAxes = axes(formalFigure);
    set(formalAxes, XScale="log", YScale="log");
    formalUse = frequencyHz >= 1 & frequencyHz <= 1e3 & ...
        ensembleAsdVPerSqrtHz > 0;
    loglog(formalAxes, frequencyHz(formalUse), ...
        ensembleAsdVPerSqrtHz(formalUse), ...
        Color=[0.85, 0.325, 0.098], LineWidth=1.15, ...
        DisplayName=sprintf( ...
        "20-run %.3g s Welch PSD average, %.0f%% overlap", ...
        segmentDurationSeconds, 100*segmentOverlapFraction));
    hold(formalAxes, "on");
    formalOctaveUse = octaveFrequencyHz >= 1 & ...
        octaveFrequencyHz <= 1e3;
    loglog(formalAxes, octaveFrequencyHz(formalOctaveUse), ...
        ensembleOctaveAsdVPerSqrtHz(formalOctaveUse), ...
        Color=[0.25, 0.25, 0.25], LineWidth=1.4, ...
        LineStyle="--", ...
        DisplayName="Optional 1/12-octave power trend");
    loglog(formalAxes, octaveFrequencyHz(oneHzIndex), ...
        ensembleOctaveAsdVPerSqrtHz(oneHzIndex), "ko", ...
        MarkerFaceColor="k", MarkerSize=6, ...
        DisplayName=sprintf("1 Hz: %.4g V/rtHz", ...
        ensembleAsd1HzVPerSqrtHz));
    hold(formalAxes, "off");
    grid(formalAxes, "on");
    xlim(formalAxes, [1, 1e3]);
    xlabel(formalAxes, "Frequency (Hz)");
    ylabel(formalAxes, "Voltage noise density (V/\surdHz)");
    title(formalAxes, ...
        "Formal 1 Hz-1 kHz noise ASD - 8 s Welch, 50% overlap");
    legend(formalAxes, Location="best", Interpreter="none");
    savefig(formalFigure, fullfile(outputFolder, ...
        "Average_FFT_1Hz_to_1kHz.fig"));
    exportgraphics(formalFigure, fullfile(outputFolder, ...
        "Average_FFT_1Hz_to_1kHz.png"), Resolution=pngResolution);
end

%% Figure 3: run-to-run stability
stabilityFigure = figure(Name="Run stability", Color="w", ...
    Position=[140, 140, 1200, 760]);
layout = tiledlayout(stabilityFigure, 2, 1, ...
    TileSpacing="compact", Padding="compact");

nexttile(layout);
plot(runNumbers, 1e6*acRmsVByRun, "o-", LineWidth=1.1, ...
    MarkerFaceColor=[0.0000, 0.4470, 0.7410]);
grid on;
xlabel("Run");
ylabel("AC RMS (uV)");
title("Time-domain AC RMS by run");
xticks(runNumbers);

nexttile(layout);
plot(runNumbers, 1e6*asd1HzVPerSqrtHzByRun, "o-", ...
    LineWidth=1.1, MarkerFaceColor=[0.8500, 0.3250, 0.0980]);
grid on;
xlabel("Run");
ylabel("1 Hz ASD (uV/\surdHz)");
title("1 Hz-centered 1/12-octave ASD by run");
xticks(runNumbers);

title(layout, "Twenty-run measurement stability");
savefig(stabilityFigure, fullfile(outputFolder, "Run_Stability.fig"));
exportgraphics(stabilityFigure, ...
    fullfile(outputFolder, "Run_Stability.png"), ...
    Resolution=pngResolution);

%% Human-readable summary
summaryPath = fullfile(outputFolder, "Analysis_Summary.txt");
summaryFile = fopen(summaryPath, "w");
assert(summaryFile >= 0, "Could not create %s.", summaryPath);
summaryCleanup = onCleanup(@() fclose(summaryFile));
fprintf(summaryFile, "Unicorn CSA 20-run time-only TDMS noise analysis\n");
fprintf(summaryFile, "Generated: %s\n\n", ...
    string(datetime("now", Format="yyyy-MM-dd HH:mm:ss")));
fprintf(summaryFile, "Runs: %d\n", runCount);
fprintf(summaryFile, ...
    "Waveform unit assumption: TDMS numeric values are volts (unit metadata blank).\n");
fprintf(summaryFile, "Samples/run: %d\n", referenceSampleCount);
fprintf(summaryFile, "Sample rate: %.12g Hz\n", referenceSampleRateHz);
fprintf(summaryFile, "Actual capture duration N/Fs: %.12g s\n", ...
    referenceSampleCount/referenceSampleRateHz);
fprintf(summaryFile, "Analysis profile: %s\n", analysisProfile);
fprintf(summaryFile, "Segmentation: %s\n", segmentationMode);
fprintf(summaryFile, "Segments/run: %d\n", ...
    referenceFftInfo.segmentCount);
fprintf(summaryFile, "Segment duration: %.12g s\n", ...
    referenceFftInfo.segmentDurationSeconds);
fprintf(summaryFile, "Segment overlap: %.6g %%\n", ...
    100*referenceFftInfo.overlapFraction);
fprintf(summaryFile, "Discarded tail: %d samples (%.12g s)\n", ...
    referenceFftInfo.discardedSamples, ...
    referenceFftInfo.discardedSamples/referenceSampleRateHz);
fprintf(summaryFile, "Window: %s (periodic)\n", windowName);
fprintf(summaryFile, "FFT length: %d\n", referenceFftInfo.fftLength);
fprintf(summaryFile, "Bin spacing: %.12g Hz\n", ...
    referenceFftInfo.binSpacingHz);
fprintf(summaryFile, "ENBW: %.12g Hz\n", referenceFftInfo.enbwHz);
fprintf(summaryFile, "1 Hz ensemble ASD: %.12g V/sqrt(Hz)\n", ...
    ensembleAsd1HzVPerSqrtHz);
fprintf(summaryFile, "Integrated noise 1-25 kHz: %.12g Vrms\n", ...
    ensembleIntegratedNoise1To25kVrms);
fprintf(summaryFile, "Mean AC RMS across runs: %.12g V\n", ...
    mean(acRmsVByRun));
fprintf(summaryFile, "AC RMS range: %.12g to %.12g V\n", ...
    min(acRmsVByRun), max(acRmsVByRun));
fprintf(summaryFile, "Flagged runs (not excluded): %s\n", ...
    mat2str(runNumbers(isOutlier).'));
fprintf(summaryFile, "Exact duplicate runs: %s\n", ...
    duplicateDescription(runNumbers, duplicateOfRun));
fprintf(summaryFile, "Duplicate policy: duplicates are flagged but retained " + ...
    "with equal weight in the requested 20-run average.\n");
fprintf(summaryFile, "Independent waveform count after de-duplication: %d\n", ...
    independentRunCount);
fprintf(summaryFile, "De-duplicated 1 Hz ASD: %.12g V/sqrt(Hz) (%+.4f%% vs 20-file result)\n", ...
    deduplicatedAsd1HzVPerSqrtHz, deduplicatedDifference1HzPercent);
fprintf(summaryFile, "50 Hz spur: %.9g Hz, %.9g V/sqrt(Hz), +/-0.5 Hz integrated %.9g Vrms\n", ...
    spur50FrequencyHz, spur50AsdVPerSqrtHz, spur50IntegratedVrms);
fprintf(summaryFile, "150 Hz-region spur: %.9g Hz, %.9g V/sqrt(Hz), +/-0.5 Hz integrated %.9g Vrms\n", ...
    spur150FrequencyHz, spur150AsdVPerSqrtHz, spur150IntegratedVrms);
fprintf(summaryFile, "High-frequency RMS-ASD roll-off (10 kHz-25 kHz vs 1 kHz-10 kHz): %.6f dB ensemble\n", ...
    ensembleRollOff10kTo25kVs1kTo10kDb);
fprintf(summaryFile, "Per-run roll-off mean/std: %.6f / %.6f dB\n", ...
    mean(rollOff10kTo25kVs1kTo10kDbByRun), ...
    std(rollOff10kTo25kVs1kTo10kDbByRun));
fprintf(summaryFile, "Interpretation: the high-frequency roll-off is repeatable across runs; " + ...
    "a calibrated flat reference is needed to separate DUT and acquisition-chain response.\n");
fprintf(summaryFile, "\nAveraging rule: every file has equal weight; " + ...
    "PSD (V^2/Hz) is averaged before square root.\n");
fprintf(summaryFile, "Fractional-octave curves are display-frequency " + ...
    "power averages and do not replace the full-resolution FFT data.\n");
clear summaryCleanup;

fprintf("\nAnalysis complete.\n");
fprintf("  Output folder: %s\n", outputFolder);
fprintf("  1 Hz ensemble ASD: %.6g V/sqrt(Hz)\n", ...
    ensembleAsd1HzVPerSqrtHz);
fprintf("  Integrated noise 1-25 kHz: %.6g Vrms\n", ...
    ensembleIntegratedNoise1To25kVrms);
fprintf("  Flagged runs (retained in average): %s\n", ...
    mat2str(runNumbers(isOutlier).'));
fprintf("  Exact duplicate runs (retained): %s\n", ...
    duplicateDescription(runNumbers, duplicateOfRun));

%% Local functions
function [runNumbers, order] = parseAndSortRunNumbers(fileNames)
runNumbers = nan(numel(fileNames), 1);
for index = 1:numel(fileNames)
    token = regexp(fileNames(index), "\((\d+)\)\.tdms$", ...
        "tokens", "once");
    assert(~isempty(token), ...
        "Could not parse '(run number)' from TDMS file: %s", ...
        fileNames(index));
    runNumbers(index) = str2double(token{1});
end
assert(numel(unique(runNumbers)) == numel(runNumbers), ...
    "Duplicate run numbers were found in TDMS file names.");
[runNumbers, order] = sort(runNumbers, "ascend");
end

function [voltageV, sampleRateHz, startTimeSeconds, channelName] = ...
        readChannel0Waveform(tdmsPath, channelSearchText)
fileInfo = tdmsinfo(tdmsPath);
channelList = fileInfo.ChannelList;
channelNames = string(channelList.ChannelName);
groupNames = string(channelList.ChannelGroupName);
dataTypes = string(channelList.DataType);

matches = contains(lower(channelNames), lower(channelSearchText)) & ...
    contains(lower(groupNames), "waveform data") & ...
    strcmpi(dataTypes, "Double") & ~contains(lower(channelNames), "fft");
rows = find(matches);
assert(numel(rows) == 1, ...
    "Expected one time-domain Channel 0 in %s; found %d.", ...
    tdmsPath, numel(rows));

row = rows(1);
channelName = channelNames(row);
groupName = groupNames(row);
channelProperties = tdmsreadprop(tdmsPath, ...
    ChannelGroupName=groupName, ChannelName=channelName);
sampleIntervalSeconds = getNumericProperty( ...
    channelProperties, "wf_increment");
startTimeSeconds = getNumericProperty( ...
    channelProperties, "wf_start_offset");
assert(isfinite(sampleIntervalSeconds) && sampleIntervalSeconds > 0, ...
    "Invalid sample interval in %s.", tdmsPath);
sampleRateHz = 1/sampleIntervalSeconds;

selectedData = tdmsread(tdmsPath, ...
    ChannelGroupName=groupName, ChannelNames=channelName);
voltageV = double(selectedData{1}{:, 1});
lastValid = find(~ismissing(voltageV), 1, "last");
assert(~isempty(lastValid), "Channel 0 contains no samples in %s.", tdmsPath);
voltageV = voltageV(1:lastValid);
assert(isreal(voltageV) && all(isfinite(voltageV)), ...
    "Channel 0 contains missing, infinite, or complex values in %s.", ...
    tdmsPath);
voltageV = voltageV(:);
end

function value = getNumericProperty(propertyTable, propertyName)
variableNames = string(propertyTable.Properties.VariableNames);
index = find(strcmpi(variableNames, propertyName), 1, "first");
assert(~isempty(index), "TDMS property '%s' was not found.", propertyName);
value = double(propertyTable{1, index});
end

function [frequencyHz, psdV2PerHz, fftInfo] = estimateSegmentedPsd( ...
        voltageV, sampleRateHz, windowName, removeMean, ...
        segmentationMode, segmentDurationSeconds, overlapFraction)
voltageV = double(voltageV(:));
sampleCount = numel(voltageV);
normalizedMode = lower(string(segmentationMode));

assert(overlapFraction >= 0 && overlapFraction < 1, ...
    "Overlap fraction must be in [0, 1).");
switch normalizedMode
    case "whole-record"
        segmentLength = sampleCount;
        overlapSamples = 0;
    case "fixed-duration"
        segmentLength = round(segmentDurationSeconds*sampleRateHz);
        assert(segmentLength >= 2 && segmentLength <= sampleCount, ...
            "Fixed segment length %d is invalid for %d samples.", ...
            segmentLength, sampleCount);
        overlapSamples = floor(overlapFraction*segmentLength);
    otherwise
        error("Unknown segmentation mode: %s", segmentationMode);
end

hopSamples = segmentLength-overlapSamples;
segmentStarts = (1:hopSamples:(sampleCount-segmentLength+1)).';
segmentCount = numel(segmentStarts);
assert(segmentCount >= 1, "No complete segment is available.");

window = periodicWindow(windowName, segmentLength);
windowPower = sum(window.^2);
oneSidedLength = floor(segmentLength/2)+1;
psdAccumulator = zeros(oneSidedLength, 1);
timeDomainWindowedPowerAccumulator = 0;

for segmentIndex = 1:segmentCount
    firstSample = segmentStarts(segmentIndex);
    segment = voltageV(firstSample:firstSample+segmentLength-1);
    if removeMean
        segment = segment-mean(segment);
    end
    segmentFft = fft(segment.*window, segmentLength);
    timeDomainWindowedPowerAccumulator = ...
        timeDomainWindowedPowerAccumulator + ...
        sum(abs(segment.*window).^2)/windowPower;
    segmentPsd = abs(segmentFft(1:oneSidedLength)).^2 / ...
        (sampleRateHz*windowPower);
    if rem(segmentLength, 2) == 0
        if oneSidedLength > 2
            segmentPsd(2:end-1) = 2*segmentPsd(2:end-1);
        end
    else
        segmentPsd(2:end) = 2*segmentPsd(2:end);
    end
    psdAccumulator = psdAccumulator+segmentPsd;
end

psdV2PerHz = psdAccumulator/segmentCount;
frequencyHz = (0:oneSidedLength-1).' * ...
    (sampleRateHz/segmentLength);
timeDomainWindowedRms = sqrt( ...
    timeDomainWindowedPowerAccumulator/segmentCount);
frequencyDomainRms = sqrt(sum(psdV2PerHz) * ...
    (sampleRateHz/segmentLength));
parsevalRelativeError = abs(frequencyDomainRms-timeDomainWindowedRms) / ...
    max(timeDomainWindowedRms, realmin);
assert(parsevalRelativeError < 1e-10, ...
    "PSD normalization check failed (relative error %.3g).", ...
    parsevalRelativeError);

fftInfo = struct;
fftInfo.segmentationMode = normalizedMode;
fftInfo.windowName = string(windowName);
fftInfo.fftLength = segmentLength;
fftInfo.segmentDurationSeconds = segmentLength/sampleRateHz;
fftInfo.segmentCount = segmentCount;
fftInfo.overlapSamples = overlapSamples;
fftInfo.overlapFraction = overlapSamples/segmentLength;
fftInfo.discardedSamples = sampleCount - ...
    (segmentStarts(end)+segmentLength-1);
fftInfo.binSpacingHz = sampleRateHz/segmentLength;
fftInfo.enbwHz = sampleRateHz*sum(window.^2)/sum(window)^2;
fftInfo.enbwBins = fftInfo.enbwHz/fftInfo.binSpacingHz;
fftInfo.removeMean = removeMean;
fftInfo.timeDomainWindowedRms = timeDomainWindowedRms;
fftInfo.frequencyDomainIntegratedRms = frequencyDomainRms;
fftInfo.parsevalRelativeError = parsevalRelativeError;
end

function window = periodicWindow(windowName, sampleCount)
n = (0:sampleCount-1).';
normalizedName = lower(erase(string(windowName), ...
    [" ", "-", "_"]));
switch normalizedName
    case {"none", "rectangular", "rectwin", "uniform"}
        window = ones(sampleCount, 1);
    case {"hann", "hanning"}
        window = 0.5-0.5*cos(2*pi*n/sampleCount);
    case "hamming"
        window = 0.54-0.46*cos(2*pi*n/sampleCount);
    case "blackman"
        window = 0.42-0.5*cos(2*pi*n/sampleCount) + ...
            0.08*cos(4*pi*n/sampleCount);
    case "blackmanharris"
        window = 0.35875-0.48829*cos(2*pi*n/sampleCount) + ...
            0.14128*cos(4*pi*n/sampleCount) - ...
            0.01168*cos(6*pi*n/sampleCount);
    otherwise
        error("Unsupported FFT window: %s", windowName);
end
end

function [centerFrequencyHz, averagePsd] = ...
        fractionalOctavePsdAverage(frequencyHz, psd, ...
        bandsPerOctave, frequencyRangeHz)
frequencyHz = double(frequencyHz(:));
psd = double(psd(:));
assert(numel(frequencyHz) == numel(psd), ...
    "Frequency and PSD vectors must have equal length.");

anchorHz = 1;
firstBand = ceil(bandsPerOctave*log2(frequencyRangeHz(1)/anchorHz));
lastBand = floor(bandsPerOctave*log2(frequencyRangeHz(2)/anchorHz));
bandIndices = (firstBand:lastBand).';
centerFrequencyHz = anchorHz*2.^(bandIndices/bandsPerOctave);
edgeIndices = ((firstBand-0.5):(lastBand+0.5)).';
bandEdgesHz = anchorHz*2.^(edgeIndices/bandsPerOctave);

frequencyStepHz = median(diff(frequencyHz));
averagePsd = nan(numel(bandIndices), 1);
for bandIndex = 1:numel(bandIndices)
    bandLowHz = bandEdgesHz(bandIndex);
    bandHighHz = bandEdgesHz(bandIndex+1);
    if bandLowHz < frequencyHz(1) || bandHighHz > frequencyHz(end)
        continue;
    end

    firstRawIndex = max(1, ceil(1 + ...
        (bandLowHz-frequencyStepHz/2-frequencyHz(1))/frequencyStepHz));
    lastRawIndex = min(numel(frequencyHz), floor(1 + ...
        (bandHighHz+frequencyStepHz/2-frequencyHz(1))/frequencyStepHz));
    rawIndices = (firstRawIndex:lastRawIndex).';
    rawBinLowHz = frequencyHz(rawIndices)-frequencyStepHz/2;
    rawBinHighHz = frequencyHz(rawIndices)+frequencyStepHz/2;
    overlapHz = max(0, min(rawBinHighHz, bandHighHz) - ...
        max(rawBinLowHz, bandLowHz));
    valid = overlapHz > 0 & isfinite(psd(rawIndices)) & ...
        psd(rawIndices) >= 0;
    coveredHz = sum(overlapHz(valid));
    if coveredHz > 0
        averagePsd(bandIndex) = ...
            sum(psd(rawIndices(valid)).*overlapHz(valid))/coveredHz;
    end
end

populated = isfinite(averagePsd);
centerFrequencyHz = centerFrequencyHz(populated);
averagePsd = averagePsd(populated);
end

function assertSameGrid(referenceHz, candidateHz, label, filePath)
referenceHz = double(referenceHz(:));
candidateHz = double(candidateHz(:));
assert(numel(referenceHz) == numel(candidateHz), ...
    "%s length mismatch in %s.", label, filePath);
toleranceHz = max(1e-12, 1e-10*max(1, abs(referenceHz(end))));
assert(abs(referenceHz(1)-candidateHz(1)) <= toleranceHz && ...
    abs(referenceHz(end)-candidateHz(end)) <= toleranceHz, ...
    "%s grid mismatch in %s.", label, filePath);
end

function value = integrateNoise(frequencyHz, psd, lowHz, highHz)
use = frequencyHz >= lowHz & frequencyHz <= highHz;
assert(nnz(use) >= 2, "Insufficient frequency bins for integration.");
frequencyStepHz = median(diff(frequencyHz));
value = sqrt(sum(psd(use))*frequencyStepHz);
end

function value = bandRmsAsd(frequencyHz, psd, lowHz, highHz)
use = frequencyHz >= lowHz & frequencyHz < highHz;
assert(any(use), "No FFT bins are present in %.6g to %.6g Hz.", ...
    lowHz, highHz);
value = sqrt(mean(psd(use)));
end

function [peakFrequencyHz, peakAsd] = peakAsdInBand( ...
        frequencyHz, asd, lowHz, highHz)
use = frequencyHz >= lowHz & frequencyHz <= highHz;
assert(any(use), "No FFT bins are present in %.6g to %.6g Hz.", ...
    lowHz, highHz);
candidateFrequencyHz = frequencyHz(use);
candidateAsd = asd(use);
[peakAsd, peakIndex] = max(candidateAsd);
peakFrequencyHz = candidateFrequencyHz(peakIndex);
end

function flag = robustOutlierFlag(values)
values = double(values(:));
center = median(values);
absoluteDeviation = abs(values-center);
scaledMad = 1.4826*median(absoluteDeviation);
if scaledMad == 0 || ~isfinite(scaledMad)
    flag = false(size(values));
else
    flag = absoluteDeviation > 3*scaledMad;
end
end

function signature = waveformSignature(voltageV)
voltageV = double(voltageV(:));
middleIndex = round((numel(voltageV)+1)/2);
signature = [numel(voltageV), sum(voltageV), sum(voltageV.^2), ...
    min(voltageV), max(voltageV), voltageV(1), ...
    voltageV(middleIndex), voltageV(end)];
end

function text = duplicateDescription(runNumbers, duplicateOfRun)
duplicateIndices = find(~isnan(duplicateOfRun));
if isempty(duplicateIndices)
    text = "none";
    return;
end
pairs = strings(numel(duplicateIndices), 1);
for index = 1:numel(duplicateIndices)
    runIndex = duplicateIndices(index);
    pairs(index) = sprintf("Run %d = Run %d", ...
        runNumbers(runIndex), duplicateOfRun(runIndex));
end
text = strjoin(pairs, "; ");
end
