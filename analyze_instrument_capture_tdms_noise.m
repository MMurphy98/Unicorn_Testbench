%% Analyze Channel 0 noise from an InstrumentStudio TDMS capture
% This script reads the Channel 0 time waveform, calculates a one-sided
% voltage amplitude spectral density (ASD) in V/sqrt(Hz), and compares it
% with the FFT trace exported by InstrumentStudio in the same TDMS file.
%
% Requirement: MATLAB R2022a or newer with Data Acquisition Toolbox.
% Signal Processing Toolbox is not required; the window and PSD scaling
% are implemented locally below.
%
% Important for this particular capture:
%   * Channel 0 contains 1,100,002 samples (about 22 s at 50 kSa/s).
%   * The InstrumentStudio FFT used 2,000,000 samples (40 s) and exported
%     1,000,001 bins at 0.025 Hz spacing.
% The saved time waveform therefore cannot reproduce the device FFT
% bin-for-bin.  Their statistically averaged noise floors can still be
% compared when the same Hamming-window ENBW normalization is used.

clearvars;
close all;
clc;

%% User settings
scriptFullPath = string(mfilename("fullpath"));
if strlength(scriptFullPath) == 0
    dataFolder = string(pwd);
else
    dataFolder = string(fileparts(scriptFullPath));
end

% Exact file name or wildcard pattern.  For a 20-capture ensemble, keep
% only the intended files under one specific prefix, for example
% "Noise_1Hz_Run*.tdms", and use that pattern here.
tdmsFilePattern = "Instrument Capture*.tdms";
maximumCaptureCount = 20; % safety cap; narrow the pattern if exceeded

channelSearchText = "Channel 0";
deviceFftSearchText = "FFT 1 (Channel 0)";

% Remove the approximately -58.9 mV DC component before calculating the
% MATLAB noise spectrum.  This avoids DC/window leakage in the first bins.
removeMeanBeforeFFT = true;

% "auto" uses the InstrumentStudio FFT window stored in the panel JSON.
% For this file it resolves to "Hamming".
matlabWindowName = "auto";

% PSD segmentation mode:
%   "whole-record"   Each TDMS time record is one FFT segment.  This is
%                    recommended for 20 independent 22 s captures because
%                    it preserves df ~= 0.04545 Hz and the 1 Hz detail.
%   "fixed-duration" Split every capture into overlapping Welch segments.
%                    This is smoother but sacrifices frequency resolution.
segmentationMode = "whole-record";
segmentDurationSeconds = 8; % used only for "fixed-duration"
segmentOverlapFraction = 0.5;

% The x-axis is logarithmic.  Start at 1 Hz because the device's first
% positive bin is dominated by Hamming-window leakage from the DC offset.
plotFrequencyRangeHz = [1, inf];

% Noise density is usually easiest to inspect with a logarithmic y-axis.
% Change to "linear" if only the x-axis should be logarithmic.
spectrumYScale = "log";

% Smooth the displayed spectrum by averaging POWER (V^2/Hz) in
% logarithmically spaced fractional-octave bands, then taking the square
% root.  This keeps the full 22 s FFT for low-frequency resolution while
% averaging many neighboring bins in the high-frequency half.
useFractionalOctaveAverage = true;
fractionalOctaveBandsPerOctave = 12; % 12 = 1/12 octave; 6 or 3 is smoother
showRawSpectra = false;              % true overlays the unsmoothed FFTs

% Optional band statistics.  Each row is [lower upper] in hertz.
comparisonBandsHz = [100, 1e3; 1e3, 10e3; 10e3, 25e3];

% Set true to save the two figures beside the TDMS file.
saveFigures = false;

%% Inspect and read the TDMS file
tdmsPaths = resolveTdmsFiles( ...
    dataFolder, tdmsFilePattern, maximumCaptureCount);
captureCount = numel(tdmsPaths);
tdmsPath = tdmsPaths(1);
[~, firstFileStem, firstFileExtension] = fileparts(tdmsPath);
tdmsFileName = firstFileStem + firstFileExtension;

fileInfo = tdmsinfo(tdmsPath);
channelList = fileInfo.ChannelList;
allGroups = tdmsread(tdmsPath);

timeRow = findTdmsChannel(channelList, channelSearchText, ...
    "Waveform Data", false);
[voltage, timeGroupNumber, timeColumnNumber] = readTdmsColumn( ...
    allGroups, channelList, timeRow);

timeGroupName = string(channelList.ChannelGroupName(timeRow));
timeChannelName = string(channelList.ChannelName(timeRow));
timeProperties = tdmsreadprop(tdmsPath, ...
    ChannelGroupName=timeGroupName, ChannelName=timeChannelName);

sampleIntervalSeconds = getNumericProperty(timeProperties, "wf_increment");
timeStartSeconds = getNumericProperty(timeProperties, "wf_start_offset");
sampleRateHz = 1/sampleIntervalSeconds;
sampleCount = numel(voltage);
timeSeconds = timeStartSeconds + (0:sampleCount-1).' * sampleIntervalSeconds;

assert(isreal(voltage) && all(isfinite(voltage)), ...
    "Channel 0 must contain finite real-valued samples.");

%% Read InstrumentStudio panel settings and device FFT trace
panelSettings = readPanelSettings(allGroups, channelList);
firstInstrumentSettings = extractInstrumentSettings( ...
    panelSettings, channelSearchText);
deviceWindowName = firstInstrumentSettings.windowName;
deviceAveragingMode = firstInstrumentSettings.averagingMode;
configuredSampleRateHz = firstInstrumentSettings.sampleRateHz;
configuredRecordLength = firstInstrumentSettings.recordLength;
configuredRbwHz = firstInstrumentSettings.rbwHz;
configuredFftUnits = firstInstrumentSettings.fftUnits;

if strcmpi(matlabWindowName, "auto")
    matlabWindowName = deviceWindowName;
end

deviceFftRow = findTdmsChannel(channelList, deviceFftSearchText, ...
    "Waveform Data", true);
[deviceDbv, deviceGroupNumber, deviceColumnNumber] = readTdmsColumn( ...
    allGroups, channelList, deviceFftRow);

deviceGroupName = string(channelList.ChannelGroupName(deviceFftRow));
deviceChannelName = string(channelList.ChannelName(deviceFftRow));
deviceProperties = tdmsreadprop(tdmsPath, ...
    ChannelGroupName=deviceGroupName, ChannelName=deviceChannelName);

deviceFrequencyStartHz = getNumericProperty( ...
    deviceProperties, "wf_start_offset");
deviceBinSpacingHz = getNumericProperty(deviceProperties, "wf_increment");
deviceFrequencyHz = deviceFrequencyStartHz + ...
    (0:numel(deviceDbv)-1).' * deviceBinSpacingHz;

% A one-sided real FFT with M bins normally came from N=2*(M-1) samples.
inferredDeviceFftLength = 2*(numel(deviceDbv)-1);
if isfinite(configuredRecordLength) && ...
        floor(configuredRecordLength/2)+1 == numel(deviceDbv)
    deviceFftLength = configuredRecordLength;
else
    deviceFftLength = inferredDeviceFftLength;
end

inferredDeviceSampleRateHz = deviceFftLength * deviceBinSpacingHz;
if isfinite(configuredSampleRateHz)
    deviceSampleRateHz = configuredSampleRateHz;
else
    deviceSampleRateHz = inferredDeviceSampleRateHz;
end

%% MATLAB one-sided noise ASD: V/sqrt(Hz)
[matlabFrequencyHz, matlabPsdV2PerHz, ~, matlabFftInfo] = ...
    segmentedNoiseAsd(voltage, sampleRateHz, matlabWindowName, ...
    removeMeanBeforeFFT, segmentationMode, segmentDurationSeconds, ...
    segmentOverlapFraction);

%% Convert the InstrumentStudio dBV/bin FFT to V/sqrt(Hz)
% InstrumentStudio's dBV trace in this capture is a one-sided,
% RMS-equivalent voltage amplitude per FFT bin.  For windowed noise, the
% conversion must divide by sqrt(ENBW), not merely sqrt(bin spacing):
%
%   Vrms/bin = 10^(dBV/20)
%   ASD      = (Vrms/bin)/sqrt(ENBW)       [V/sqrt(Hz)]
%
% ENBW = Fs*sum(w.^2)/sum(w)^2.
deviceWindow = periodicWindow(deviceWindowName, deviceFftLength);
deviceEnbwHz = deviceSampleRateHz * sum(deviceWindow.^2) / ...
    sum(deviceWindow)^2;
deviceVrmsPerBin = 10.^(deviceDbv/20);
deviceAsdVPerSqrtHz = deviceVrmsPerBin/sqrt(deviceEnbwHz);
devicePsdV2PerHz = deviceAsdVPerSqrtHz.^2;

%% Average equal-weight PSD estimates across all matching capture files
% Each file contributes one equal-weight PSD estimate.  In whole-record
% mode that estimate is one full 22 s periodogram.  In fixed-duration mode
% it is the Welch power average of all complete segments in that file.
matlabPsdAccumulator = matlabPsdV2PerHz;
devicePsdAccumulator = devicePsdV2PerHz;

captureFile = strings(captureCount, 1);
captureSamples = zeros(captureCount, 1);
captureSampleRateHz = zeros(captureCount, 1);
captureMeanV = zeros(captureCount, 1);
captureAcRmsV = zeros(captureCount, 1);
captureSegmentCount = zeros(captureCount, 1);
captureDiscardedSamples = zeros(captureCount, 1);

captureFile(1) = tdmsPath;
captureSamples(1) = sampleCount;
captureSampleRateHz(1) = sampleRateHz;
captureMeanV(1) = mean(voltage);
captureAcRmsV(1) = sqrt(mean((voltage-mean(voltage)).^2));
captureSegmentCount(1) = matlabFftInfo.segmentCount;
captureDiscardedSamples(1) = matlabFftInfo.discardedSamples;

for captureIndex = 2:captureCount
    currentPath = tdmsPaths(captureIndex);
    fprintf("Reading capture %d/%d: %s\n", ...
        captureIndex, captureCount, currentPath);
    currentCapture = readCaptureForBatch(currentPath, ...
        channelSearchText, deviceFftSearchText);

    assert(abs(currentCapture.sampleRateHz-sampleRateHz) <= ...
        max(1e-9*sampleRateHz, 1e-9), ...
        "Sample-rate mismatch in %s: %.12g Hz instead of %.12g Hz.", ...
        currentPath, currentCapture.sampleRateHz, sampleRateHz);
    if strcmpi(segmentationMode, "whole-record")
        assert(currentCapture.sampleCount == sampleCount, ...
            "Whole-record ensemble averaging requires equal sample " + ...
            "counts. %s contains %d samples; the first file contains %d.", ...
            currentPath, currentCapture.sampleCount, sampleCount);
    end

    [currentFrequencyHz, currentPsdV2PerHz, ~, currentFftInfo] = ...
        segmentedNoiseAsd(currentCapture.voltage, ...
        currentCapture.sampleRateHz, matlabWindowName, ...
        removeMeanBeforeFFT, segmentationMode, ...
        segmentDurationSeconds, segmentOverlapFraction);
    assertSameFrequencyGrid(matlabFrequencyHz, currentFrequencyHz, ...
        "MATLAB PSD", currentPath);
    matlabPsdAccumulator = matlabPsdAccumulator + currentPsdV2PerHz;

    currentSettings = currentCapture.instrumentSettings;
    assert(strcmpi(currentSettings.windowName, deviceWindowName), ...
        "InstrumentStudio FFT window mismatch in %s: %s instead of %s.", ...
        currentPath, currentSettings.windowName, deviceWindowName);
    assertSameFrequencyGrid(deviceFrequencyHz, ...
        currentCapture.deviceFrequencyHz, "InstrumentStudio FFT", ...
        currentPath);
    devicePsdAccumulator = devicePsdAccumulator + ...
        currentCapture.devicePsdV2PerHz;

    captureFile(captureIndex) = currentPath;
    captureSamples(captureIndex) = currentCapture.sampleCount;
    captureSampleRateHz(captureIndex) = currentCapture.sampleRateHz;
    captureMeanV(captureIndex) = mean(currentCapture.voltage);
    captureAcRmsV(captureIndex) = sqrt(mean( ...
        (currentCapture.voltage-mean(currentCapture.voltage)).^2));
    captureSegmentCount(captureIndex) = currentFftInfo.segmentCount;
    captureDiscardedSamples(captureIndex) = ...
        currentFftInfo.discardedSamples;
end

% Equal-file ensemble average in linear power units.
matlabPsdV2PerHz = matlabPsdAccumulator/captureCount;
matlabAsdVPerSqrtHz = sqrt(matlabPsdV2PerHz);
devicePsdV2PerHz = devicePsdAccumulator/captureCount;
deviceAsdVPerSqrtHz = sqrt(devicePsdV2PerHz);

matlabFftInfo.captureCount = captureCount;
matlabFftInfo.totalSegmentCount = sum(captureSegmentCount);
matlabFftInfo.segmentCountsByCapture = captureSegmentCount;
matlabFftInfo.discardedSamplesByCapture = captureDiscardedSamples;

captureSummary = table(captureFile, captureSamples, ...
    captureSampleRateHz, captureMeanV, captureAcRmsV, ...
    captureSegmentCount, captureDiscardedSamples, ...
    VariableNames=["File", "Samples", "SampleRateHz", "MeanV", ...
    "AcRmsV", "SegmentCount", "DiscardedSamples"]);

assert(useFractionalOctaveAverage || showRawSpectra, ...
    "Enable the fractional-octave average, the raw spectra, or both.");

%% Print acquisition and normalization summary
fprintf("\nTDMS noise analysis\n");
fprintf("  Capture files:        %d\n", captureCount);
fprintf("  First file:           %s\n", tdmsPath);
fprintf("  Time channel:         %s / %s\n", ...
    timeGroupName, timeChannelName);
fprintf("  TDMS group/column:    %d / %d\n", ...
    timeGroupNumber, timeColumnNumber);
fprintf("  Samples:              %d\n", sampleCount);
fprintf("  Sample rate:          %.12g Hz\n", sampleRateHz);
fprintf("  Time range:           %.9g to %.9g s\n", ...
    timeSeconds(1), timeSeconds(end));
fprintf("  Mean voltage:         %.12g V\n", mean(voltage));
fprintf("  AC RMS voltage:       %.12g V\n", ...
    sqrt(mean((voltage-mean(voltage)).^2)));
fprintf("\nMATLAB FFT\n");
fprintf("  Segmentation mode:    %s\n", segmentationMode);
fprintf("  Window:               %s (periodic)\n", matlabFftInfo.windowName);
fprintf("  Remove mean:          %s\n", string(removeMeanBeforeFFT));
fprintf("  FFT length:           %d\n", matlabFftInfo.fftLength);
fprintf("  Segment duration:     %.9g s\n", ...
    matlabFftInfo.segmentDurationSeconds);
fprintf("  Segment overlap:      %.3g %%\n", ...
    100*matlabFftInfo.overlapFraction);
fprintf("  Segments/capture:     %s\n", ...
    mat2str(captureSegmentCount.'));
fprintf("  Total periodograms:   %d (file PSDs are equal-weighted)\n", ...
    matlabFftInfo.totalSegmentCount);
fprintf("  Bin spacing:          %.12g Hz\n", matlabFftInfo.binSpacingHz);
fprintf("  ENBW:                 %.12g Hz (%.9g bins)\n", ...
    matlabFftInfo.enbwHz, matlabFftInfo.enbwBins);
fprintf("\nInstrumentStudio FFT\n");
fprintf("  Averaged captures:    %d\n", captureCount);
fprintf("  TDMS group/column:    %d / %d\n", ...
    deviceGroupNumber, deviceColumnNumber);
fprintf("  Window:               %s (periodic)\n", deviceWindowName);
fprintf("  Averaging:            %s\n", deviceAveragingMode);
fprintf("  Exported units:       %s (%s)\n", ...
    configuredFftUnits, deviceChannelName);
fprintf("  FFT length:           %d\n", deviceFftLength);
fprintf("  Bin spacing:          %.12g Hz\n", deviceBinSpacingHz);
fprintf("  Configured RBW:       %.12g Hz\n", configuredRbwHz);
fprintf("  ENBW:                 %.12g Hz (%.9g bins)\n", ...
    deviceEnbwHz, deviceEnbwHz/deviceBinSpacingHz);
if useFractionalOctaveAverage
    fprintf("\nDisplayed average\n");
    fprintf("  Method:               1/%g-octave PSD average\n", ...
        fractionalOctaveBandsPerOctave);
    fprintf("  Operation:            mean(V^2/Hz), then sqrt\n");
end

if sampleCount ~= deviceFftLength
    warning("The TDMS time waveform contains %d samples, but the " + ...
        "device FFT used %d samples. Exact bin-for-bin reproduction is " + ...
        "not possible; compare the stationary noise floor by band.", ...
        sampleCount, deviceFftLength);
end

printBandComparison(comparisonBandsHz, ...
    matlabFrequencyHz, matlabPsdV2PerHz, ...
    deviceFrequencyHz, devicePsdV2PerHz);

%% Plot Channel 0 time-domain waveform
timeFigure = figure(Name="Channel 0 time waveform", Color="w");
plot(timeSeconds, voltage, Color=[0.0000, 0.4470, 0.7410], ...
    LineWidth=0.8);
grid on;
xlabel("Time relative to trigger (s)");
ylabel("Channel 0 voltage (V)");
title("InstrumentStudio Channel 0 time waveform (first capture)", ...
    Interpreter="none");

%% Plot MATLAB and InstrumentStudio noise spectra
matlabUse = matlabFrequencyHz > 0 & isfinite(matlabAsdVPerSqrtHz) & ...
    matlabAsdVPerSqrtHz > 0;
deviceUse = deviceFrequencyHz > 0 & isfinite(deviceAsdVPerSqrtHz) & ...
    deviceAsdVPerSqrtHz > 0;

frequencyUpperHz = min([sampleRateHz/2, deviceFrequencyHz(end)]);
if isfinite(plotFrequencyRangeHz(2))
    frequencyUpperHz = min(frequencyUpperHz, plotFrequencyRangeHz(2));
end
frequencyLowerHz = max([plotFrequencyRangeHz(1), ...
    matlabFrequencyHz(find(matlabUse, 1, "first")), ...
    deviceFrequencyHz(find(deviceUse, 1, "first"))]);

if useFractionalOctaveAverage
    [matlabAverageFrequencyHz, matlabAveragePsdV2PerHz, ...
        matlabAverageBinCount] = fractionalOctavePsdAverage( ...
        matlabFrequencyHz, matlabPsdV2PerHz, ...
        fractionalOctaveBandsPerOctave, ...
        [frequencyLowerHz, frequencyUpperHz]);
    [deviceAverageFrequencyHz, deviceAveragePsdV2PerHz, ...
        deviceAverageBinCount] = fractionalOctavePsdAverage( ...
        deviceFrequencyHz, devicePsdV2PerHz, ...
        fractionalOctaveBandsPerOctave, ...
        [frequencyLowerHz, frequencyUpperHz]);
else
    matlabAverageFrequencyHz = zeros(0, 1); %#ok<UNRCH>
    matlabAveragePsdV2PerHz = zeros(0, 1);
    matlabAverageBinCount = zeros(0, 1);
    deviceAverageFrequencyHz = zeros(0, 1);
    deviceAveragePsdV2PerHz = zeros(0, 1);
    deviceAverageBinCount = zeros(0, 1);
end

spectrumFigure = figure(Name="Channel 0 noise ASD comparison", Color="w");
hold on;
plotHandles = gobjects(0);
legendText = strings(0);

if showRawSpectra
    plotHandles(end+1) = semilogx(matlabFrequencyHz(matlabUse), ...
        matlabAsdVPerSqrtHz(matlabUse), ...
        Color=[0.6500, 0.7800, 0.9000], LineWidth=0.35); %#ok<UNRCH>
    legendText(end+1) = sprintf( ...
        "MATLAB %d-capture ensemble: df=%.6g Hz", ...
        captureCount, matlabFftInfo.binSpacingHz);

    plotHandles(end+1) = semilogx(deviceFrequencyHz(deviceUse), ...
        deviceAsdVPerSqrtHz(deviceUse), ...
        Color=[0.9500, 0.7000, 0.6200], LineWidth=0.35);
    legendText(end+1) = sprintf( ...
        "InstrumentStudio %d-capture ensemble: df=%.6g Hz", ...
        captureCount, deviceBinSpacingHz);
end


if useFractionalOctaveAverage
    plotHandles(end+1) = semilogx(matlabAverageFrequencyHz, ...
        sqrt(matlabAveragePsdV2PerHz), ...
        Color=[0.0000, 0.4470, 0.7410], LineWidth=1.6);
    legendText(end+1) = sprintf( ...
        "MATLAB %d-capture, 1/%g-octave average", ...
        captureCount, fractionalOctaveBandsPerOctave);

    plotHandles(end+1) = semilogx(deviceAverageFrequencyHz, ...
        sqrt(deviceAveragePsdV2PerHz), ...
        Color=[0.8500, 0.3250, 0.0980], LineWidth=1.6);
    legendText(end+1) = sprintf( ...
        "InstrumentStudio %d-capture, 1/%g-octave average", ...
        captureCount, fractionalOctaveBandsPerOctave);
end

hold off;
grid on;
set(gca, XScale="log", YScale=spectrumYScale);
xlim([frequencyLowerHz, frequencyUpperHz]);
xlabel("Frequency (Hz)");
ylabel("Voltage noise density (V/\surdHz)");
title(sprintf("Channel 0 noise spectrum: %d-capture PSD ensemble", ...
    captureCount));
legend(plotHandles, legendText, Location="best", Interpreter="none");

if saveFigures
    [~, fileStem] = fileparts(tdmsFileName); %#ok<UNRCH>
    exportgraphics(timeFigure, ...
        fullfile(dataFolder, fileStem + sprintf( ...
        "_%dcapture_channel0_time.png", captureCount)), ...
        Resolution=180);
    exportgraphics(spectrumFigure, ...
        fullfile(dataFolder, fileStem + sprintf( ...
        "_%dcapture_noise_asd_compare.png", captureCount)), ...
        Resolution=180);
end

%% Leave reusable numeric results in the MATLAB workspace
analysisResults = struct;
analysisResults.tdmsPath = tdmsPath;
analysisResults.tdmsPaths = tdmsPaths;
analysisResults.captureCount = captureCount;
analysisResults.captureSummary = captureSummary;
analysisResults.channelName = timeChannelName;
analysisResults.exampleCapturePath = tdmsPath;
analysisResults.timeSeconds = timeSeconds;
analysisResults.voltageV = voltage;
analysisResults.sampleRateHz = sampleRateHz;
analysisResults.settings.tdmsFilePattern = tdmsFilePattern;
analysisResults.settings.segmentationMode = segmentationMode;
analysisResults.settings.segmentDurationSeconds = segmentDurationSeconds;
analysisResults.settings.segmentOverlapFraction = segmentOverlapFraction;
analysisResults.settings.windowName = matlabWindowName;
analysisResults.matlab.frequencyHz = matlabFrequencyHz;
analysisResults.matlab.psdV2PerHz = matlabPsdV2PerHz;
analysisResults.matlab.asdVPerSqrtHz = matlabAsdVPerSqrtHz;
analysisResults.matlab.ensemblePsdV2PerHz = matlabPsdV2PerHz;
analysisResults.matlab.ensembleAsdVPerSqrtHz = matlabAsdVPerSqrtHz;
analysisResults.matlab.info = matlabFftInfo;
analysisResults.matlab.averageFrequencyHz = matlabAverageFrequencyHz;
analysisResults.matlab.averagePsdV2PerHz = matlabAveragePsdV2PerHz;
analysisResults.matlab.averageAsdVPerSqrtHz = ...
    sqrt(matlabAveragePsdV2PerHz);
analysisResults.matlab.averageRawBinCount = matlabAverageBinCount;
analysisResults.instrumentStudio.frequencyHz = deviceFrequencyHz;
analysisResults.instrumentStudio.dbvPerBin = deviceDbv;
analysisResults.instrumentStudio.psdV2PerHz = devicePsdV2PerHz;
analysisResults.instrumentStudio.asdVPerSqrtHz = deviceAsdVPerSqrtHz;
analysisResults.instrumentStudio.ensemblePsdV2PerHz = ...
    devicePsdV2PerHz;
analysisResults.instrumentStudio.ensembleAsdVPerSqrtHz = ...
    deviceAsdVPerSqrtHz;
analysisResults.instrumentStudio.windowName = deviceWindowName;
analysisResults.instrumentStudio.averagingMode = deviceAveragingMode;
analysisResults.instrumentStudio.fftLength = deviceFftLength;
analysisResults.instrumentStudio.binSpacingHz = deviceBinSpacingHz;
analysisResults.instrumentStudio.enbwHz = deviceEnbwHz;
analysisResults.instrumentStudio.captureCount = captureCount;
analysisResults.instrumentStudio.averageFrequencyHz = ...
    deviceAverageFrequencyHz;
analysisResults.instrumentStudio.averagePsdV2PerHz = ...
    deviceAveragePsdV2PerHz;
analysisResults.instrumentStudio.averageAsdVPerSqrtHz = ...
    sqrt(deviceAveragePsdV2PerHz);
analysisResults.instrumentStudio.averageRawBinCount = ...
    deviceAverageBinCount;
analysisResults.frequencyAverage.bandsPerOctave = ...
    fractionalOctaveBandsPerOctave;

%% Local functions
function tdmsPaths = resolveTdmsFiles(dataFolder, filePattern, maximumCount)
listing = dir(fullfile(dataFolder, filePattern));
listing = listing(~[listing.isdir]);
assert(~isempty(listing), ...
    "No TDMS files match '%s' under %s.", filePattern, dataFolder);
assert(isinf(maximumCount) || ...
    (isfinite(maximumCount) && maximumCount >= 1 && ...
    maximumCount == floor(maximumCount)), ...
    "maximumCaptureCount must be a positive integer or inf.");
assert(isinf(maximumCount) || numel(listing) <= maximumCount, ...
    "Pattern '%s' matched %d TDMS files, exceeding the configured " + ...
    "maximum of %d. Use a more specific pattern so unrelated captures " + ...
    "are never averaged silently.", ...
    filePattern, numel(listing), maximumCount);

% Chronological ordering makes per-file summaries reproducible.  Ordering
% does not affect the equal-file ensemble mean.
[~, order] = sort([listing.datenum], "ascend");
listing = listing(order);
tdmsPaths = fullfile(string({listing.folder}), string({listing.name})).';
end

function capture = readCaptureForBatch(tdmsPath, ...
        channelSearchText, deviceFftSearchText)
fileInfo = tdmsinfo(tdmsPath);
channelList = fileInfo.ChannelList;
allGroups = tdmsread(tdmsPath);

timeRow = findTdmsChannel(channelList, channelSearchText, ...
    "Waveform Data", false);
[voltage, ~, ~] = readTdmsColumn(allGroups, channelList, timeRow);
timeGroupName = string(channelList.ChannelGroupName(timeRow));
timeChannelName = string(channelList.ChannelName(timeRow));
timeProperties = tdmsreadprop(tdmsPath, ...
    ChannelGroupName=timeGroupName, ChannelName=timeChannelName);
sampleIntervalSeconds = getNumericProperty( ...
    timeProperties, "wf_increment");
assert(isfinite(sampleIntervalSeconds) && sampleIntervalSeconds > 0, ...
    "Invalid Channel 0 sample interval in %s.", tdmsPath);

panelSettings = readPanelSettings(allGroups, channelList);
instrumentSettings = extractInstrumentSettings( ...
    panelSettings, channelSearchText);

deviceFftRow = findTdmsChannel(channelList, deviceFftSearchText, ...
    "Waveform Data", true);
[deviceDbv, ~, ~] = readTdmsColumn( ...
    allGroups, channelList, deviceFftRow);
deviceGroupName = string(channelList.ChannelGroupName(deviceFftRow));
deviceChannelName = string(channelList.ChannelName(deviceFftRow));
deviceProperties = tdmsreadprop(tdmsPath, ...
    ChannelGroupName=deviceGroupName, ChannelName=deviceChannelName);
deviceFrequencyStartHz = getNumericProperty( ...
    deviceProperties, "wf_start_offset");
deviceBinSpacingHz = getNumericProperty( ...
    deviceProperties, "wf_increment");
assert(isfinite(deviceBinSpacingHz) && deviceBinSpacingHz > 0, ...
    "Invalid InstrumentStudio FFT bin spacing in %s.", tdmsPath);

deviceFrequencyHz = deviceFrequencyStartHz + ...
    (0:numel(deviceDbv)-1).' * deviceBinSpacingHz;
inferredDeviceFftLength = 2*(numel(deviceDbv)-1);
if isfinite(instrumentSettings.recordLength) && ...
        floor(instrumentSettings.recordLength/2)+1 == numel(deviceDbv)
    deviceFftLength = instrumentSettings.recordLength;
else
    deviceFftLength = inferredDeviceFftLength;
end

if isfinite(instrumentSettings.sampleRateHz)
    deviceSampleRateHz = instrumentSettings.sampleRateHz;
else
    deviceSampleRateHz = deviceFftLength*deviceBinSpacingHz;
end
deviceWindow = periodicWindow( ...
    instrumentSettings.windowName, deviceFftLength);
deviceEnbwHz = deviceSampleRateHz*sum(deviceWindow.^2) / ...
    sum(deviceWindow)^2;
devicePsdV2PerHz = 10.^(deviceDbv/10)/deviceEnbwHz;

capture = struct;
capture.path = string(tdmsPath);
capture.voltage = voltage;
capture.sampleCount = numel(voltage);
capture.sampleRateHz = 1/sampleIntervalSeconds;
capture.instrumentSettings = instrumentSettings;
capture.deviceFrequencyHz = deviceFrequencyHz;
capture.devicePsdV2PerHz = devicePsdV2PerHz;
capture.deviceEnbwHz = deviceEnbwHz;
capture.deviceFftLength = deviceFftLength;
end

function settings = extractInstrumentSettings(panelSettings, channelSearchText)
settings = struct;
settings.windowName = "Hamming";
settings.averagingMode = "unknown";
settings.sampleRateHz = nan;
settings.recordLength = nan;
settings.rbwHz = nan;
settings.fftUnits = "unknown";

if isempty(panelSettings)
    return;
end

try
    instrumentConfiguration = ...
        panelSettings.Instrument.InstrumentConfiguration;
    fftChannels = instrumentConfiguration.FFTChannels;
    fftSources = string({fftChannels.FFTSource});
    fftConfigIndex = find(contains(lower(fftSources), ...
        lower(channelSearchText)), 1, "first");
    if isempty(fftConfigIndex)
        fftConfigIndex = 1;
    end

    settings.windowName = string(fftChannels(fftConfigIndex).Window);
    settings.averagingMode = string( ...
        fftChannels(fftConfigIndex).FFTAveragingMode);
    settings.sampleRateHz = double( ...
        instrumentConfiguration.Timing.ManualSampleRate);
    settings.recordLength = double( ...
        instrumentConfiguration.Timing.ManualRecordLength);
    settings.rbwHz = double( ...
        instrumentConfiguration.FrequencyDomainGraphSettings.RBW);
    settings.fftUnits = string( ...
        instrumentConfiguration.FrequencyDomainGraphSettings.FFTUnits);
catch settingsException
    settingsMessage = "Could not decode InstrumentStudio settings: " + ...
        string(settingsException.message);
    warning("TDMSNoise:PanelSettings", "%s", settingsMessage);
end
end

function assertSameFrequencyGrid(referenceHz, candidateHz, label, filePath)
referenceHz = double(referenceHz(:));
candidateHz = double(candidateHz(:));
assert(numel(referenceHz) == numel(candidateHz), ...
    "%s grid length mismatch in %s: %d instead of %d.", ...
    label, filePath, numel(candidateHz), numel(referenceHz));

scaleHz = max([1; abs(referenceHz([1, end]))]);
toleranceHz = max(1e-12, 1e-10*scaleHz);
assert(abs(referenceHz(1)-candidateHz(1)) <= toleranceHz && ...
    abs(referenceHz(end)-candidateHz(end)) <= toleranceHz, ...
    "%s frequency grid mismatch in %s.", label, filePath);
end

function row = findTdmsChannel(channelList, channelText, groupText, isFft)
channelNames = lower(string(channelList.ChannelName));
groupNames = lower(string(channelList.ChannelGroupName));
dataTypes = lower(string(channelList.DataType));

matches = contains(channelNames, lower(channelText)) & ...
    contains(groupNames, lower(groupText)) & dataTypes == "double";
if isFft
    matches = matches & contains(channelNames, "fft");
else
    matches = matches & ~contains(channelNames, "fft");
end

rows = find(matches);
assert(numel(rows) == 1, ...
    "Expected one TDMS channel matching '%s'; found %d.", ...
    channelText, numel(rows));
row = rows(1);
end

function [values, groupNumber, columnNumber] = readTdmsColumn( ...
        allGroups, channelList, row)
groupNumber = double(channelList.ChannelGroupNumber(row));
rowsInGroup = find(channelList.ChannelGroupNumber == groupNumber);
columnNumber = find(rowsInGroup == row, 1, "first");

assert(groupNumber >= 1 && groupNumber <= numel(allGroups), ...
    "TDMS group number %d is not present in tdmsread output.", groupNumber);
assert(~isempty(columnNumber), "Could not map TDMS channel to table column.");

rawValues = allGroups{groupNumber}{:, columnNumber};
lastDataRow = find(~ismissing(rawValues), 1, "last");
assert(~isempty(lastDataRow), "Selected TDMS channel contains no data.");

values = double(rawValues(1:lastDataRow));
assert(~any(ismissing(values)), ...
    "Selected TDMS channel contains missing values inside its data range.");
values = values(:);
end

function value = getNumericProperty(propertyTable, propertyName)
variableNames = string(propertyTable.Properties.VariableNames);
index = find(strcmpi(variableNames, propertyName), 1, "first");
assert(~isempty(index), "TDMS property '%s' was not found.", propertyName);
value = double(propertyTable{1, index});
end

function panelSettings = readPanelSettings(allGroups, channelList)
panelSettings = [];
groupNames = lower(string(channelList.ChannelGroupName));
dataTypes = lower(string(channelList.DataType));
row = find(contains(groupNames, "panel configurations") & ...
    dataTypes == "string", 1, "first");
if isempty(row)
    warning("InstrumentStudio panel configuration was not found in TDMS.");
    return;
end

groupNumber = double(channelList.ChannelGroupNumber(row));
rowsInGroup = find(channelList.ChannelGroupNumber == groupNumber);
columnNumber = find(rowsInGroup == row, 1, "first");
configurationText = string(allGroups{groupNumber}{1, columnNumber});

try
    panelSettings = jsondecode(configurationText);
catch jsonException
    jsonMessage = "InstrumentStudio panel JSON could not be decoded: " + ...
        string(jsonException.message);
    warning("TDMSNoise:PanelJson", "%s", jsonMessage);
end
end

function [frequencyHz, psdV2PerHz, asdVPerSqrtHz, fftInfo] = ...
        segmentedNoiseAsd(voltage, sampleRateHz, windowName, removeMean, ...
        segmentationMode, segmentDurationSeconds, overlapFraction)
% Estimate one equal-weight file PSD from either the complete record or
% the Welch power average of complete fixed-duration segments.
voltage = double(voltage(:));
sampleCount = numel(voltage);
normalizedMode = lower(string(segmentationMode));

assert(isreal(voltage) && all(isfinite(voltage)), ...
    "Voltage waveform must contain finite real samples.");
assert(sampleRateHz > 0 && isfinite(sampleRateHz), ...
    "Sample rate must be finite and positive.");
assert(overlapFraction >= 0 && overlapFraction < 1, ...
    "Segment overlap fraction must be in [0, 1).");

switch normalizedMode
    case "whole-record"
        segmentLength = sampleCount;
        overlapSamples = 0;
        effectiveOverlapFraction = 0;
    case "fixed-duration"
        assert(isfinite(segmentDurationSeconds) && ...
            segmentDurationSeconds > 0, ...
            "Fixed segment duration must be finite and positive.");
        segmentLength = round(segmentDurationSeconds*sampleRateHz);
        assert(segmentLength >= 2 && segmentLength <= sampleCount, ...
            "Fixed segment duration produces %d samples; it must be " + ...
            "between 2 and the record length %d.", ...
            segmentLength, sampleCount);
        overlapSamples = floor(overlapFraction*segmentLength);
        effectiveOverlapFraction = overlapSamples/segmentLength;
    otherwise
        error("Unknown segmentationMode '%s'. Use 'whole-record' or " + ...
            "'fixed-duration'.", segmentationMode);
end

hopSamples = segmentLength-overlapSamples;
segmentStarts = (1:hopSamples:(sampleCount-segmentLength+1)).';
segmentCount = numel(segmentStarts);
assert(segmentCount >= 1, "No complete FFT segment is available.");

window = periodicWindow(windowName, segmentLength);
windowPower = sum(window.^2);
oneSidedLength = floor(segmentLength/2)+1;
psdAccumulator = zeros(oneSidedLength, 1);

for segmentIndex = 1:segmentCount
    firstSample = segmentStarts(segmentIndex);
    segment = voltage(firstSample:firstSample+segmentLength-1);
    if removeMean
        % Remove each segment's mean independently to prevent DC leakage.
        segment = segment-mean(segment);
    end

    segmentFft = fft(segment.*window, segmentLength);
    segmentPsd = abs(segmentFft(1:oneSidedLength)).^2 / ...
        (sampleRateHz*windowPower);

    % Convert to a one-sided PSD.  DC and an even-length Nyquist bin are
    % unique and are not doubled.
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
asdVPerSqrtHz = sqrt(psdV2PerHz);

lastUsedSample = segmentStarts(end)+segmentLength-1;
fftInfo = struct;
fftInfo.segmentationMode = normalizedMode;
fftInfo.windowName = string(windowName);
fftInfo.fftLength = segmentLength;
fftInfo.segmentLength = segmentLength;
fftInfo.segmentDurationSeconds = segmentLength/sampleRateHz;
fftInfo.overlapSamples = overlapSamples;
fftInfo.overlapFraction = effectiveOverlapFraction;
fftInfo.hopSamples = hopSamples;
fftInfo.segmentCount = segmentCount;
fftInfo.discardedSamples = sampleCount-lastUsedSample;
fftInfo.binSpacingHz = sampleRateHz/segmentLength;
fftInfo.enbwHz = sampleRateHz*sum(window.^2)/sum(window)^2;
fftInfo.enbwBins = fftInfo.enbwHz/fftInfo.binSpacingHz;
fftInfo.removeMean = removeMean;
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
        error("Unsupported FFT window '%s'.", windowName);
end
end

function [centerFrequencyHz, averagePsd, rawBinCount] = ...
        fractionalOctavePsdAverage(frequencyHz, psd, ...
        bandsPerOctave, frequencyRangeHz)
% Average PSD, rather than ASD, so noise power remains unbiased.
frequencyHz = double(frequencyHz(:));
psd = double(psd(:));

assert(numel(frequencyHz) == numel(psd), ...
    "Frequency and PSD vectors must have equal lengths.");
assert(isfinite(bandsPerOctave) && bandsPerOctave >= 1 && ...
    bandsPerOctave == floor(bandsPerOctave), ...
    "bandsPerOctave must be a positive integer.");
assert(all(isfinite(frequencyRangeHz)) && ...
    frequencyRangeHz(1) > 0 && ...
    frequencyRangeHz(2) > frequencyRangeHz(1), ...
    "Fractional-octave averaging requires a finite positive range.");

% Anchor the logarithmic grid at exactly 1 Hz.  For 12 bands per octave,
% the 1 Hz band spans approximately 0.9715 to 1.0293 Hz, while higher
% bands naturally contain progressively more raw FFT bins.
anchorFrequencyHz = 1;
firstBandIndex = ceil(bandsPerOctave * ...
    log2(frequencyRangeHz(1)/anchorFrequencyHz));
lastBandIndex = floor(bandsPerOctave * ...
    log2(frequencyRangeHz(2)/anchorFrequencyHz));
assert(lastBandIndex >= firstBandIndex, ...
    "Frequency range is too narrow for fractional-octave averaging.");

bandIndices = (firstBandIndex:lastBandIndex).';
centerFrequencyHz = anchorFrequencyHz * ...
    2.^(bandIndices/bandsPerOctave);
edgeIndices = ((firstBandIndex-0.5):(lastBandIndex+0.5)).';
bandEdgesHz = anchorFrequencyHz * ...
    2.^(edgeIndices/bandsPerOctave);

bandCount = numel(bandIndices);
averagePsd = nan(bandCount, 1);
rawBinCount = zeros(bandCount, 1);

frequencyStepHz = median(diff(frequencyHz));
assert(isfinite(frequencyStepHz) && frequencyStepHz > 0, ...
    "Frequency vector must be strictly increasing.");
assert(max(abs(diff(frequencyHz)-frequencyStepHz)) <= ...
    max(1e-9*frequencyStepHz, 10*eps(max(frequencyHz))), ...
    "Fractional-octave averaging expects a uniformly spaced FFT grid.");

% Weight the first and last FFT bins in each logarithmic band by their
% actual frequency overlap.  This matters near 1 Hz, where a 1/12-octave
% band is only slightly wider than one raw FFT bin.
for bandIndex = 1:bandCount
    bandLowHz = bandEdgesHz(bandIndex);
    bandHighHz = bandEdgesHz(bandIndex+1);

    % Do not report fractional bands that extend beyond available data.
    if bandLowHz < frequencyHz(1) || bandHighHz > frequencyHz(end)
        continue;
    end

    firstRawIndex = ceil(1 + ...
        (bandLowHz-frequencyStepHz/2-frequencyHz(1))/frequencyStepHz);
    lastRawIndex = floor(1 + ...
        (bandHighHz+frequencyStepHz/2-frequencyHz(1))/frequencyStepHz);
    firstRawIndex = max(firstRawIndex, 1);
    lastRawIndex = min(lastRawIndex, numel(frequencyHz));
    if lastRawIndex < firstRawIndex
        continue;
    end

    rawIndices = (firstRawIndex:lastRawIndex).';
    rawBinLowHz = frequencyHz(rawIndices)-frequencyStepHz/2;
    rawBinHighHz = frequencyHz(rawIndices)+frequencyStepHz/2;
    overlapHz = max(0, min(rawBinHighHz, bandHighHz) - ...
        max(rawBinLowHz, bandLowHz));
    valid = overlapHz > 0 & isfinite(psd(rawIndices)) & ...
        psd(rawIndices) >= 0;

    coveredBandwidthHz = sum(overlapHz(valid));
    if coveredBandwidthHz > 0
        averagePsd(bandIndex) = ...
            sum(psd(rawIndices(valid)).*overlapHz(valid)) / ...
            coveredBandwidthHz;
        rawBinCount(bandIndex) = sum(valid);
    end
end

populated = rawBinCount > 0;
centerFrequencyHz = centerFrequencyHz(populated);
averagePsd = averagePsd(populated);
rawBinCount = rawBinCount(populated);
end

function printBandComparison(bandsHz, matlabFrequencyHz, matlabPsd, ...
        deviceFrequencyHz, devicePsd)
fprintf("\nRepresentative noise density by band\n");
fprintf("  Band (Hz)          MATLAB median / RMS ASD" + ...
    "       InstrumentStudio median / RMS ASD\n");
fprintf("                     (uV/sqrt(Hz))" + ...
    "                   (uV/sqrt(Hz))\n");

for bandIndex = 1:size(bandsHz, 1)
    lowerHz = bandsHz(bandIndex, 1);
    upperHz = bandsHz(bandIndex, 2);
    matlabUse = matlabFrequencyHz >= lowerHz & ...
        matlabFrequencyHz < upperHz;
    deviceUse = deviceFrequencyHz >= lowerHz & ...
        deviceFrequencyHz < upperHz;

    if ~any(matlabUse) || ~any(deviceUse)
        fprintf("  %9.3g-%-9.3g  insufficient data\n", lowerHz, upperHz);
        continue;
    end

    matlabAsd = sqrt(matlabPsd(matlabUse));
    deviceAsd = sqrt(devicePsd(deviceUse));
    fprintf("  %9.3g-%-9.3g  %9.5f / %-9.5f        %9.5f / %-9.5f\n", ...
        lowerHz, upperHz, ...
        1e6*median(matlabAsd), 1e6*sqrt(mean(matlabAsd.^2)), ...
        1e6*median(deviceAsd), 1e6*sqrt(mean(deviceAsd.^2)));
end
end
