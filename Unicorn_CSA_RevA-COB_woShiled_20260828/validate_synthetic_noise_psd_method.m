%% Validate the InstrumentStudio time-domain noise PSD method synthetically
% This script uses the same acquisition conditions as the 2026-08-28 data:
% 50 kSa/s, 1,100,002 samples (22.00004 s), 20 independent records, a
% periodic Hamming window, and a one-sided PSD in V^2/Hz.
%
% The validation is intentionally independent of TDMS input.  It checks the
% explicit production formula against MATLAB's PERIOD0GRAM and PWELCH,
% generates white noise with a known ASD, and generates a bin-centered sine
% with known RMS amplitude.  It also demonstrates why multiple records must
% be averaged in PSD (power) before taking the square root.
%
% Requirement: MATLAB R2022a or newer with Signal Processing Toolbox.

clearvars;
close all;
clc;

%% Output location
scriptPath = string(mfilename("fullpath"));
assert(strlength(scriptPath) > 0, ...
    "Run this file as a MATLAB script so its output path can be resolved.");
scriptFolder = string(fileparts(scriptPath));
outputFolder = fullfile(scriptFolder, "validation_results");
if ~isfolder(outputFolder)
    mkdir(outputFolder);
end

%% Synthetic acquisition settings (identical to the measured records)
settings = struct;
settings.randomSeed = 20260828;
settings.sampleRateHz = 50e3;
settings.sampleCount = 1100002;
settings.runCount = 20;
settings.windowName = "periodic Hamming";
settings.removeMean = true;
settings.bandsPerOctave = 12;
settings.plotFrequencyRangeHz = [1, 25e3];
settings.broadbandCheckHz = [100, 10e3];
settings.integratedNoiseBandHz = [1, 25e3];

% Ten low-noise and ten high-noise records make the averaging-order check
% observable.  The correct ensemble ASD is the RMS of the per-run ASDs.
lowAsdVPerSqrtHz = 4e-6;
highAsdVPerSqrtHz = 8e-6;
inputAsdVPerSqrtHzByRun = repmat( ...
    [lowAsdVPerSqrtHz; highAsdVPerSqrtHz], settings.runCount/2, 1);
expectedEnsembleAsdVPerSqrtHz = ...
    sqrt(mean(inputAsdVPerSqrtHzByRun.^2));
expectedArithmeticMeanAsdVPerSqrtHz = ...
    mean(inputAsdVPerSqrtHzByRun);

rng(settings.randomSeed, "twister");
sampleRateHz = settings.sampleRateHz;
sampleCount = settings.sampleCount;
runCount = settings.runCount;
frequencyBinSpacingHz = sampleRateHz/sampleCount;

oneSidedLength = floor(sampleCount/2)+1;
psdSumV2PerHz = zeros(oneSidedLength, 1);
rawAsdSumVPerSqrtHz = zeros(oneSidedLength, 1);
perRunBroadbandAsdVPerSqrtHz = zeros(runCount, 1);
perRunParsevalRelativeError = zeros(runCount, 1);
octavePsdV2PerHzByRun = [];

periodogramNormalizedError = nan;
pwelchNormalizedError = nan;
referenceFrequencyErrorHz = nan;
hammingWindowError = nan;

fprintf("Synthetic white-noise validation: %d runs x %d samples...\n", ...
    runCount, sampleCount);

%% Case A: known white-noise ASD and 20-run ensemble averaging
for runIndex = 1:runCount
    targetAsd = inputAsdVPerSqrtHzByRun(runIndex);
    % For real discrete white noise, one-sided PSD = 2*sigma^2/Fs.
    sigmaV = targetAsd*sqrt(sampleRateHz/2);
    waveformV = sigmaV*randn(sampleCount, 1);

    [currentFrequencyHz, currentPsdV2PerHz, currentInfo] = ...
        explicitProductionPsd(waveformV, sampleRateHz, true);

    if runIndex == 1
        frequencyHz = currentFrequencyHz;
        broadbandMask = frequencyHz >= settings.broadbandCheckHz(1) & ...
            frequencyHz < settings.broadbandCheckHz(2);

        centeredWaveformV = waveformV-mean(waveformV);
        matlabWindow = hamming(sampleCount, "periodic");
        explicitWindow = periodicHamming(sampleCount);
        hammingWindowError = max(abs(matlabWindow-explicitWindow));

        [matlabPeriodogramPsd, matlabPeriodogramFrequencyHz] = ...
            periodogram(centeredWaveformV, matlabWindow, sampleCount, ...
            sampleRateHz, "onesided");
        [matlabPwelchPsd, matlabPwelchFrequencyHz] = ...
            pwelch(centeredWaveformV, matlabWindow, 0, sampleCount, ...
            sampleRateHz, "onesided");

        referenceFrequencyErrorHz = max([ ...
            max(abs(frequencyHz-matlabPeriodogramFrequencyHz)), ...
            max(abs(frequencyHz-matlabPwelchFrequencyHz))]);
        periodogramNormalizedError = max(abs( ...
            currentPsdV2PerHz-matlabPeriodogramPsd)) / ...
            max(matlabPeriodogramPsd);
        pwelchNormalizedError = max(abs( ...
            currentPsdV2PerHz-matlabPwelchPsd)) / ...
            max(matlabPwelchPsd);
    else
        assert(isequal(frequencyHz, currentFrequencyHz), ...
            "Synthetic runs produced different FFT frequency grids.");
    end

    [currentOctaveFrequencyHz, currentOctavePsdV2PerHz] = ...
        fractionalOctavePsdAverage(currentFrequencyHz, ...
        currentPsdV2PerHz, settings.bandsPerOctave, ...
        settings.plotFrequencyRangeHz);
    if runIndex == 1
        octaveFrequencyHz = currentOctaveFrequencyHz;
        octavePsdV2PerHzByRun = zeros( ...
            numel(octaveFrequencyHz), runCount);
    else
        assert(isequal(octaveFrequencyHz, currentOctaveFrequencyHz), ...
            "Synthetic runs produced different octave grids.");
    end

    psdSumV2PerHz = psdSumV2PerHz+currentPsdV2PerHz;
    rawAsdSumVPerSqrtHz = ...
        rawAsdSumVPerSqrtHz+sqrt(currentPsdV2PerHz);
    octavePsdV2PerHzByRun(:, runIndex) = ...
        currentOctavePsdV2PerHz; %#ok<SAGROW>
    perRunBroadbandAsdVPerSqrtHz(runIndex) = ...
        sqrt(mean(currentPsdV2PerHz(broadbandMask)));
    perRunParsevalRelativeError(runIndex) = ...
        currentInfo.parsevalRelativeError;

    fprintf("  Run %02d: target %.3f uV/sqrt(Hz), measured %.3f uV/sqrt(Hz)\n", ...
        runIndex, 1e6*targetAsd, ...
        1e6*perRunBroadbandAsdVPerSqrtHz(runIndex));
end

ensemblePsdV2PerHz = psdSumV2PerHz/runCount;
ensembleAsdVPerSqrtHz = sqrt(ensemblePsdV2PerHz);
incorrectRawAsdAverageVPerSqrtHz = rawAsdSumVPerSqrtHz/runCount;

ensembleOctavePsdV2PerHz = mean(octavePsdV2PerHzByRun, 2);
ensembleOctaveAsdVPerSqrtHz = sqrt(ensembleOctavePsdV2PerHz);
incorrectOctaveAsdAverageVPerSqrtHz = ...
    mean(sqrt(octavePsdV2PerHzByRun), 2);

% Linearity check: octave smoothing before or after ensemble PSD averaging
% must be identical because the smoother is a weighted linear PSD average.
[octaveFrequencyFromMeanHz, octavePsdFromMeanV2PerHz] = ...
    fractionalOctavePsdAverage(frequencyHz, ensemblePsdV2PerHz, ...
    settings.bandsPerOctave, settings.plotFrequencyRangeHz);
assert(isequal(octaveFrequencyHz, octaveFrequencyFromMeanHz), ...
    "Octave grid differs when smoothing the ensemble PSD.");
octaveLinearityRelativeError = max(abs( ...
    ensembleOctavePsdV2PerHz-octavePsdFromMeanV2PerHz)) / ...
    max(ensembleOctavePsdV2PerHz);

ensembleBroadbandAsdVPerSqrtHz = ...
    sqrt(mean(ensemblePsdV2PerHz(broadbandMask)));
arithmeticMeanBroadbandAsdVPerSqrtHz = ...
    mean(perRunBroadbandAsdVPerSqrtHz);
incorrectRawBroadbandAsdVPerSqrtHz = ...
    mean(incorrectRawAsdAverageVPerSqrtHz(broadbandMask));

[~, oneHzIndex] = min(abs(octaveFrequencyHz-1));
oneHzOctaveAsdVPerSqrtHz = ...
    ensembleOctaveAsdVPerSqrtHz(oneHzIndex);

integratedMask = frequencyHz >= settings.integratedNoiseBandHz(1) & ...
    frequencyHz <= settings.integratedNoiseBandHz(2);
integratedNoiseVrms = sqrt(sum( ...
    ensemblePsdV2PerHz(integratedMask))*frequencyBinSpacingHz);

% Exact discrete-bin expectation.  Interior one-sided bins have ASD^2;
% the Nyquist bin of a real even-length record has half that expected PSD.
expectedPsdShapeV2PerHz = repmat( ...
    expectedEnsembleAsdVPerSqrtHz^2, oneSidedLength, 1);
expectedPsdShapeV2PerHz(end) = ...
    expectedPsdShapeV2PerHz(end)/2;
expectedIntegratedNoiseVrms = sqrt(sum( ...
    expectedPsdShapeV2PerHz(integratedMask))*frequencyBinSpacingHz);

% A flat PSD must remain exactly flat after 1/12-octave averaging.
[~, flatOctavePsd] = fractionalOctavePsdAverage( ...
    frequencyHz, expectedPsdShapeV2PerHz, ...
    settings.bandsPerOctave, settings.plotFrequencyRangeHz);
flatOctaveRelativeError = max(abs( ...
    flatOctavePsd-expectedEnsembleAsdVPerSqrtHz^2)) / ...
    expectedEnsembleAsdVPerSqrtHz^2;

%% Case B: bin-centered sine with known RMS amplitude
settings.toneBin = 1100;
settings.toneFrequencyHz = settings.toneBin*frequencyBinSpacingHz;
settings.toneRmsV = 100e-6;
settings.tonePhaseRad = 0.37;

sampleIndex = (0:sampleCount-1).';
toneWaveformV = sqrt(2)*settings.toneRmsV*sin( ...
    2*pi*settings.toneBin*sampleIndex/sampleCount + ...
    settings.tonePhaseRad);
clear sampleIndex;

[toneFrequencyHz, tonePsdV2PerHz, toneInfo] = ...
    explicitProductionPsd(toneWaveformV, sampleRateHz, true);
toneAsdVPerSqrtHz = sqrt(tonePsdV2PerHz);
toneIndex = settings.toneBin+1;
measuredTonePeakAsdVPerSqrtHz = toneAsdVPerSqrtHz(toneIndex);
expectedTonePeakAsdVPerSqrtHz = ...
    settings.toneRmsV/sqrt(toneInfo.enbwHz);

% A periodic Hamming window places a coherent tone in the center bin and
% its two neighboring bins.  A +/-2.5-bin band safely captures the main
% lobe, and its integrated PSD must recover the known sine RMS amplitude.
toneBandMask = abs(toneFrequencyHz-settings.toneFrequencyHz) <= ...
    2.5*frequencyBinSpacingHz;
measuredToneBandVrms = sqrt(sum( ...
    tonePsdV2PerHz(toneBandMask))*frequencyBinSpacingHz);

%% Acceptance metrics
metric = [
    "Explicit PSD vs MATLAB periodogram"
    "Explicit PSD vs MATLAB one-segment pwelch"
    "Frequency grid vs MATLAB references"
    "Explicit vs MATLAB periodic Hamming"
    "Maximum Parseval relative error"
    "Known ensemble broadband ASD (100 Hz-10 kHz)"
    "Known ensemble 1 Hz 1/12-octave ASD"
    "Known white-noise integrated RMS (1 Hz-25 kHz)"
    "Flat PSD through 1/12-octave smoother"
    "Octave smoothing/ensemble linearity"
    "Known coherent-tone peak ASD"
    "Known coherent-tone main-lobe RMS"
    ];

expectedValue = [
    0
    0
    0
    0
    0
    expectedEnsembleAsdVPerSqrtHz
    expectedEnsembleAsdVPerSqrtHz
    expectedIntegratedNoiseVrms
    0
    0
    expectedTonePeakAsdVPerSqrtHz
    settings.toneRmsV
    ];

measuredValue = [
    periodogramNormalizedError
    pwelchNormalizedError
    referenceFrequencyErrorHz
    hammingWindowError
    max([perRunParsevalRelativeError; toneInfo.parsevalRelativeError])
    ensembleBroadbandAsdVPerSqrtHz
    oneHzOctaveAsdVPerSqrtHz
    integratedNoiseVrms
    flatOctaveRelativeError
    octaveLinearityRelativeError
    measuredTonePeakAsdVPerSqrtHz
    measuredToneBandVrms
    ];

errorValue = [
    periodogramNormalizedError
    pwelchNormalizedError
    referenceFrequencyErrorHz
    hammingWindowError
    max([perRunParsevalRelativeError; toneInfo.parsevalRelativeError])
    abs(ensembleBroadbandAsdVPerSqrtHz/ ...
        expectedEnsembleAsdVPerSqrtHz-1)
    abs(oneHzOctaveAsdVPerSqrtHz/expectedEnsembleAsdVPerSqrtHz-1)
    abs(integratedNoiseVrms/expectedIntegratedNoiseVrms-1)
    flatOctaveRelativeError
    octaveLinearityRelativeError
    abs(measuredTonePeakAsdVPerSqrtHz/ ...
        expectedTonePeakAsdVPerSqrtHz-1)
    abs(measuredToneBandVrms/settings.toneRmsV-1)
    ];

acceptanceLimit = [
    1e-11
    1e-11
    1e-12
    1e-12
    1e-12
    0.01
    0.30
    0.01
    1e-12
    1e-12
    1e-8
    1e-8
    ];

errorDefinition = [
    "max|P-Pref|/max(Pref)"
    "max|P-Pref|/max(Pref)"
    "maximum absolute frequency error"
    "maximum absolute window-coefficient error"
    "|RMSfreq-RMStime|/RMStime"
    "absolute relative error"
    "absolute relative error; relaxed for low statistical DOF"
    "absolute relative error"
    "maximum relative error"
    "maximum relative error"
    "absolute relative error"
    "absolute relative error"
    ];

unit = [
    "ratio"
    "ratio"
    "Hz"
    "coefficient"
    "ratio"
    "V/sqrt(Hz)"
    "V/sqrt(Hz)"
    "Vrms"
    "ratio"
    "ratio"
    "V/sqrt(Hz)"
    "Vrms"
    ];

pass = errorValue <= acceptanceLimit;
metricsTable = table(metric, expectedValue, measuredValue, errorValue, ...
    acceptanceLimit, pass, errorDefinition, unit, ...
    VariableNames=["Metric", "ExpectedValue", "MeasuredValue", ...
    "ErrorValue", "AcceptanceLimit", "Pass", "ErrorDefinition", "Unit"]);

%% Save compact numeric outputs
spectrumTable = table(octaveFrequencyHz, ...
    ensembleOctaveAsdVPerSqrtHz, ...
    incorrectOctaveAsdAverageVPerSqrtHz, ...
    repmat(expectedEnsembleAsdVPerSqrtHz, ...
        numel(octaveFrequencyHz), 1), ...
    VariableNames=["Frequency_Hz", ...
    "PSD_First_Ensemble_ASD_V_per_rtHz", ...
    "Incorrect_Direct_ASD_Average_V_per_rtHz", ...
    "Expected_Ensemble_ASD_V_per_rtHz"]);

perRunTable = table((1:runCount).', inputAsdVPerSqrtHzByRun, ...
    perRunBroadbandAsdVPerSqrtHz, ...
    VariableNames=["Run", "Target_ASD_V_per_rtHz", ...
    "Measured_ASD_100Hz_10kHz_V_per_rtHz"]);

metricsCsvPath = fullfile(outputFolder, ...
    "Synthetic_Validation_Metrics.csv");
spectrumCsvPath = fullfile(outputFolder, ...
    "Synthetic_Validation_Spectrum_1over12Octave.csv");
perRunCsvPath = fullfile(outputFolder, ...
    "Synthetic_Validation_Per_Run.csv");
writetable(metricsTable, metricsCsvPath);
writetable(spectrumTable, spectrumCsvPath);
writetable(perRunTable, perRunCsvPath);

caseResults = struct;
caseResults.expectedEnsembleAsdVPerSqrtHz = ...
    expectedEnsembleAsdVPerSqrtHz;
caseResults.measuredEnsembleBroadbandAsdVPerSqrtHz = ...
    ensembleBroadbandAsdVPerSqrtHz;
caseResults.measuredOneHzOctaveAsdVPerSqrtHz = ...
    oneHzOctaveAsdVPerSqrtHz;
caseResults.expectedArithmeticMeanAsdVPerSqrtHz = ...
    expectedArithmeticMeanAsdVPerSqrtHz;
caseResults.measuredArithmeticMeanBroadbandAsdVPerSqrtHz = ...
    arithmeticMeanBroadbandAsdVPerSqrtHz;
caseResults.incorrectRawBroadbandAsdVPerSqrtHz = ...
    incorrectRawBroadbandAsdVPerSqrtHz;
caseResults.correctVsArithmeticMeanDb = 20*log10( ...
    ensembleBroadbandAsdVPerSqrtHz / ...
    arithmeticMeanBroadbandAsdVPerSqrtHz);
caseResults.expectedIntegratedNoiseVrms = expectedIntegratedNoiseVrms;
caseResults.measuredIntegratedNoiseVrms = integratedNoiseVrms;
caseResults.expectedTonePeakAsdVPerSqrtHz = ...
    expectedTonePeakAsdVPerSqrtHz;
caseResults.measuredTonePeakAsdVPerSqrtHz = ...
    measuredTonePeakAsdVPerSqrtHz;
caseResults.measuredToneBandVrms = measuredToneBandVrms;
caseResults.periodogramNormalizedError = periodogramNormalizedError;
caseResults.pwelchNormalizedError = pwelchNormalizedError;
caseResults.maximumParsevalRelativeError = ...
    max([perRunParsevalRelativeError; toneInfo.parsevalRelativeError]);
caseResults.allTestsPassed = all(pass);

matPath = fullfile(outputFolder, "Synthetic_Validation.mat");
save(matPath, "settings", "caseResults", "metricsTable", ...
    "inputAsdVPerSqrtHzByRun", "perRunBroadbandAsdVPerSqrtHz", ...
    "frequencyHz", "ensemblePsdV2PerHz", ...
    "ensembleAsdVPerSqrtHz", "octaveFrequencyHz", ...
    "ensembleOctaveAsdVPerSqrtHz", ...
    "incorrectOctaveAsdAverageVPerSqrtHz", ...
    "toneFrequencyHz", "tonePsdV2PerHz", "toneAsdVPerSqrtHz", ...
    "-v7.3");

%% Plot validation cases
figureHandle = figure(Visible="off", Color="w", ...
    Units="pixels", Position=[100, 100, 1600, 950], ...
    Name="Synthetic noise PSD validation");
layout = tiledlayout(figureHandle, 2, 2, ...
    TileSpacing="compact", Padding="compact");

axesHandle = nexttile(layout, 1);
loglog(axesHandle, octaveFrequencyHz, ...
    1e6*ensembleOctaveAsdVPerSqrtHz, ...
    Color=[0.00, 0.45, 0.74], LineWidth=1.8, ...
    DisplayName="Correct: sqrt(mean PSD)");
hold(axesHandle, "on");
loglog(axesHandle, octaveFrequencyHz, ...
    1e6*incorrectOctaveAsdAverageVPerSqrtHz, "--", ...
    Color=[0.85, 0.33, 0.10], LineWidth=1.2, ...
    DisplayName="Incorrect: mean ASD");
yline(axesHandle, 1e6*expectedEnsembleAsdVPerSqrtHz, ":k", ...
    LineWidth=1.4, DisplayName="Known PSD-first target");
xlim(axesHandle, settings.plotFrequencyRangeHz);
grid(axesHandle, "on");
xlabel(axesHandle, "Frequency (Hz)");
ylabel(axesHandle, "ASD (uV/sqrt(Hz))");
title(axesHandle, "Known white noise, 20-run ensemble");
legend(axesHandle, Location="southwest");

axesHandle = nexttile(layout, 2);
toneZoom = abs(toneFrequencyHz-settings.toneFrequencyHz) <= 0.5;
plot(axesHandle, toneFrequencyHz(toneZoom), ...
    1e6*toneAsdVPerSqrtHz(toneZoom), ...
    Color=[0.49, 0.18, 0.56], LineWidth=1.5);
hold(axesHandle, "on");
yline(axesHandle, 1e6*expectedTonePeakAsdVPerSqrtHz, ":k", ...
    LineWidth=1.3, DisplayName="Expected center-bin ASD");
grid(axesHandle, "on");
xlim(axesHandle, [settings.toneFrequencyHz-0.5, ...
    settings.toneFrequencyHz+0.5]);
ylim(axesHandle, [0, 1.1e6*expectedTonePeakAsdVPerSqrtHz]);
xlabel(axesHandle, "Frequency (Hz)");
ylabel(axesHandle, "ASD (uV/sqrt(Hz))");
title(axesHandle, sprintf( ...
    "50 Hz coherent tone: %.3f uVrms recovered", ...
    1e6*measuredToneBandVrms));

axesHandle = nexttile(layout, 3);
plot(axesHandle, 1:runCount, ...
    1e6*inputAsdVPerSqrtHzByRun, "ko-", ...
    LineWidth=1.0, MarkerFaceColor="k", DisplayName="Target");
hold(axesHandle, "on");
plot(axesHandle, 1:runCount, ...
    1e6*perRunBroadbandAsdVPerSqrtHz, "s-", ...
    Color=[0.00, 0.45, 0.74], LineWidth=1.0, ...
    MarkerFaceColor=[0.00, 0.45, 0.74], DisplayName="Measured");
grid(axesHandle, "on");
xlabel(axesHandle, "Synthetic run");
ylabel(axesHandle, "100 Hz-10 kHz ASD (uV/sqrt(Hz))");
title(axesHandle, "Per-run known noise levels");
legend(axesHandle, Location="best");

axesHandle = nexttile(layout, 4);
comparisonValues = 1e6*[ ...
    expectedEnsembleAsdVPerSqrtHz, ...
    ensembleBroadbandAsdVPerSqrtHz, ...
    expectedArithmeticMeanAsdVPerSqrtHz, ...
    arithmeticMeanBroadbandAsdVPerSqrtHz];
bar(axesHandle, comparisonValues, FaceColor="flat");
axesHandle.Children.CData = [
    0.30, 0.30, 0.30
    0.00, 0.45, 0.74
    0.65, 0.65, 0.65
    0.85, 0.33, 0.10
    ];
axesHandle.XTick = 1:4;
axesHandle.XTickLabel = {"PSD target", "PSD measured", ...
    "Mean-ASD target", "Mean-ASD measured"};
axesHandle.XTickLabelRotation = 18;
grid(axesHandle, "on");
ylabel(axesHandle, "ASD (uV/sqrt(Hz))");
title(axesHandle, sprintf( ...
    "PSD-first is %+.3f dB vs mean ASD", ...
    caseResults.correctVsArithmeticMeanDb));

title(layout, ...
    "Synthetic validation of the InstrumentStudio time-domain PSD method");

pngPath = fullfile(outputFolder, "Synthetic_Noise_Validation.png");
figPath = fullfile(outputFolder, "Synthetic_Noise_Validation.fig");
exportgraphics(figureHandle, pngPath, Resolution=240);
savefig(figureHandle, figPath);
close(figureHandle);

%% Human-readable summary
summaryPath = fullfile(outputFolder, "Synthetic_Validation_Summary.txt");
summaryFile = fopen(summaryPath, "w");
assert(summaryFile >= 0, "Could not create validation summary: %s", ...
    summaryPath);
fprintf(summaryFile, "Synthetic validation of InstrumentStudio noise PSD method\n");
fprintf(summaryFile, "========================================================\n");
fprintf(summaryFile, "MATLAB: %s\n", version);
fprintf(summaryFile, "Random seed: %d\n", settings.randomSeed);
fprintf(summaryFile, "Fs: %.12g Hz\n", sampleRateHz);
fprintf(summaryFile, "N: %d samples\n", sampleCount);
fprintf(summaryFile, "Record duration N/Fs: %.12g s\n", ...
    sampleCount/sampleRateHz);
fprintf(summaryFile, "FFT bin spacing: %.12g Hz\n", ...
    frequencyBinSpacingHz);
fprintf(summaryFile, "Hamming ENBW: %.12g Hz\n\n", toneInfo.enbwHz);

fprintf(summaryFile, "White-noise ensemble case\n");
fprintf(summaryFile, "  Input levels: 10 x %.6g and 10 x %.6g V/sqrt(Hz)\n", ...
    lowAsdVPerSqrtHz, highAsdVPerSqrtHz);
fprintf(summaryFile, "  Correct theoretical sqrt(mean ASD^2): %.12g V/sqrt(Hz)\n", ...
    expectedEnsembleAsdVPerSqrtHz);
fprintf(summaryFile, "  Measured 100 Hz-10 kHz: %.12g V/sqrt(Hz)\n", ...
    ensembleBroadbandAsdVPerSqrtHz);
fprintf(summaryFile, "  Measured 1 Hz 1/12-octave: %.12g V/sqrt(Hz)\n", ...
    oneHzOctaveAsdVPerSqrtHz);
fprintf(summaryFile, "  Incorrect theoretical arithmetic mean ASD: %.12g V/sqrt(Hz)\n", ...
    expectedArithmeticMeanAsdVPerSqrtHz);
fprintf(summaryFile, "  Measured arithmetic mean of per-run broadband ASD: %.12g V/sqrt(Hz)\n", ...
    arithmeticMeanBroadbandAsdVPerSqrtHz);
fprintf(summaryFile, "  Correct PSD-first vs arithmetic-ASD result: %+.6f dB\n", ...
    caseResults.correctVsArithmeticMeanDb);
fprintf(summaryFile, "  Expected 1 Hz-25 kHz RMS: %.12g Vrms\n", ...
    expectedIntegratedNoiseVrms);
fprintf(summaryFile, "  Measured 1 Hz-25 kHz RMS: %.12g Vrms\n\n", ...
    integratedNoiseVrms);

fprintf(summaryFile, "Coherent sine case\n");
fprintf(summaryFile, "  Tone frequency: %.12g Hz (FFT bin %d)\n", ...
    settings.toneFrequencyHz, settings.toneBin);
fprintf(summaryFile, "  Known tone RMS: %.12g Vrms\n", settings.toneRmsV);
fprintf(summaryFile, "  Expected peak ASD = Arms/sqrt(ENBW): %.12g V/sqrt(Hz)\n", ...
    expectedTonePeakAsdVPerSqrtHz);
fprintf(summaryFile, "  Measured peak ASD: %.12g V/sqrt(Hz)\n", ...
    measuredTonePeakAsdVPerSqrtHz);
fprintf(summaryFile, "  Main-lobe integrated RMS: %.12g Vrms\n\n", ...
    measuredToneBandVrms);

fprintf(summaryFile, "Independent reference checks\n");
fprintf(summaryFile, "  Explicit formula vs MATLAB periodogram: %.12g\n", ...
    periodogramNormalizedError);
fprintf(summaryFile, "  Explicit formula vs one-segment pwelch: %.12g\n", ...
    pwelchNormalizedError);
fprintf(summaryFile, "  Maximum Parseval relative error: %.12g\n", ...
    caseResults.maximumParsevalRelativeError);
fprintf(summaryFile, "  Tests passed: %d/%d\n", nnz(pass), numel(pass));
fclose(summaryFile);

fprintf("\nValidation result: %d/%d metrics passed.\n", ...
    nnz(pass), numel(pass));
disp(metricsTable(:, ["Metric", "ExpectedValue", "MeasuredValue", ...
    "ErrorValue", "AcceptanceLimit", "Pass"]));
fprintf("Outputs: %s\n", outputFolder);

assert(all(pass), ...
    "Synthetic PSD validation failed %d of %d acceptance metrics.", ...
    nnz(~pass), numel(pass));

%% Local functions
function [frequencyHz, psdV2PerHz, info] = ...
        explicitProductionPsd(voltageV, sampleRateHz, removeMean)
%EXPLICITPRODUCTIONPSD Independent expression of the production formula.
voltageV = double(voltageV(:));
sampleCount = numel(voltageV);
if removeMean
    voltageV = voltageV-mean(voltageV);
end

window = periodicHamming(sampleCount);
windowPower = sum(window.^2);
windowedVoltageV = voltageV.*window;
voltageFft = fft(windowedVoltageV, sampleCount);
oneSidedLength = floor(sampleCount/2)+1;
psdV2PerHz = abs(voltageFft(1:oneSidedLength)).^2 / ...
    (sampleRateHz*windowPower);
if rem(sampleCount, 2) == 0
    psdV2PerHz(2:end-1) = 2*psdV2PerHz(2:end-1);
else
    psdV2PerHz(2:end) = 2*psdV2PerHz(2:end);
end

frequencyHz = (0:oneSidedLength-1).'*(sampleRateHz/sampleCount);
timeDomainWindowedRms = sqrt(sum(abs(windowedVoltageV).^2)/windowPower);
frequencyDomainIntegratedRms = sqrt( ...
    sum(psdV2PerHz)*(sampleRateHz/sampleCount));

info = struct;
info.binSpacingHz = sampleRateHz/sampleCount;
info.enbwHz = sampleRateHz*sum(window.^2)/sum(window)^2;
info.timeDomainWindowedRms = timeDomainWindowedRms;
info.frequencyDomainIntegratedRms = frequencyDomainIntegratedRms;
info.parsevalRelativeError = abs( ...
    frequencyDomainIntegratedRms-timeDomainWindowedRms) / ...
    max(timeDomainWindowedRms, realmin);
end

function window = periodicHamming(sampleCount)
sampleIndex = (0:sampleCount-1).';
window = 0.54-0.46*cos(2*pi*sampleIndex/sampleCount);
end

function [centerFrequencyHz, averagePsd] = ...
        fractionalOctavePsdAverage(frequencyHz, psd, ...
        bandsPerOctave, frequencyRangeHz)
%FRACTIONALOCTAVEPSDAVERAGE Match the production overlap-weighted smoother.
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
