%% Compare the saved wiShield and woShield 20-run noise results
% Run both analyze_20run_time_only_noise.m scripts first.  This comparison
% uses only their saved PSD results, so both sides retain identical FFT and
% averaging settings.

clearvars;
close all;
clc;

scriptPath = string(mfilename("fullpath"));
assert(strlength(scriptPath) > 0, ...
    "Run this file as a MATLAB script so paths can be resolved.");
wiFolder = string(fileparts(scriptPath));
repoFolder = string(fileparts(wiFolder));
woFolder = fullfile(repoFolder, ...
    "Unicorn_CSA_RevA-COB_woShiled_20260828");
outputFolder = fullfile(wiFolder, "analysis_results");

wiPath = fullfile(outputFolder, "Average_FFT.mat");
woPath = fullfile(woFolder, "analysis_results", "Average_FFT.mat");
assert(isfile(wiPath), "wiShield result was not found: %s", wiPath);
assert(isfile(woPath), "woShield result was not found: %s", woPath);

wi = load(wiPath);
wo = load(woPath);
assert(isequal(wi.frequencyHz, wo.frequencyHz), ...
    "Full-resolution frequency grids do not match.");
assert(isequal(wi.octaveFrequencyHz, wo.octaveFrequencyHz), ...
    "Fractional-octave frequency grids do not match.");

frequencyHz = wi.octaveFrequencyHz;
wiAsdVPerSqrtHz = wi.ensembleOctaveAsdVPerSqrtHz;
woAsdVPerSqrtHz = wo.ensembleOctaveAsdVPerSqrtHz;
wiVsWoDb = 20*log10(wiAsdVPerSqrtHz./woAsdVPerSqrtHz);

comparisonTable = table(frequencyHz, wiAsdVPerSqrtHz, ...
    woAsdVPerSqrtHz, wiVsWoDb, ...
    VariableNames=["Frequency_Hz", "wiShield_ASD_V_per_rtHz", ...
    "woShield_ASD_V_per_rtHz", "wiShield_vs_woShield_dB"]);
writetable(comparisonTable, fullfile(outputFolder, ...
    "Shielding_Comparison_1over12Octave.csv"));

targetFrequencyHz = [1; 10; 1e3];
metricName = ["ASD centered at 1 Hz"; "ASD centered at 10 Hz"; ...
    "ASD centered at 1 kHz"; "Integrated noise, 1 Hz-25 kHz"; ...
    "Peak ASD near 50 Hz"; "Peak ASD near 150 Hz"];
units = [repmat("V/sqrt(Hz)", 3, 1); "Vrms"; ...
    "V/sqrt(Hz)"; "V/sqrt(Hz)"];

wiKeyValue = zeros(6, 1);
woKeyValue = zeros(6, 1);
for index = 1:numel(targetFrequencyHz)
    wiKeyValue(index) = centeredFractionalOctaveAsd( ...
        wi.frequencyHz, wi.ensemblePsdV2PerHz, ...
        targetFrequencyHz(index), 12);
    woKeyValue(index) = centeredFractionalOctaveAsd( ...
        wo.frequencyHz, wo.ensemblePsdV2PerHz, ...
        targetFrequencyHz(index), 12);
end
wiKeyValue(4) = integrateNoise( ...
    wi.frequencyHz, wi.ensemblePsdV2PerHz, 1, 25e3);
woKeyValue(4) = integrateNoise( ...
    wo.frequencyHz, wo.ensemblePsdV2PerHz, 1, 25e3);
wiKeyValue(5) = peakAsdInBand( ...
    wi.frequencyHz, wi.ensembleAsdVPerSqrtHz, 49, 51);
woKeyValue(5) = peakAsdInBand( ...
    wo.frequencyHz, wo.ensembleAsdVPerSqrtHz, 49, 51);
wiKeyValue(6) = peakAsdInBand( ...
    wi.frequencyHz, wi.ensembleAsdVPerSqrtHz, 149, 151);
woKeyValue(6) = peakAsdInBand( ...
    wo.frequencyHz, wo.ensembleAsdVPerSqrtHz, 149, 151);
keyMetricComparison = table(metricName, wiKeyValue, woKeyValue, ...
    units, 20*log10(wiKeyValue./woKeyValue), ...
    VariableNames=["Metric", "wiShield_Value", "woShield_Value", ...
    "Unit", "wiShield_vs_woShield_dB"]);
writetable(keyMetricComparison, fullfile(outputFolder, ...
    "Shielding_Key_Metrics.csv"));

comparisonFigure = figure(Name="Shielding comparison", Color="w", ...
    Position=[100, 100, 1200, 850]);
layout = tiledlayout(comparisonFigure, 2, 1, ...
    TileSpacing="compact", Padding="compact");

topAxes = nexttile(layout);
set(topAxes, XScale="log", YScale="log");
loglog(topAxes, frequencyHz, woAsdVPerSqrtHz, ...
    LineWidth=1.8, Color=[0.15, 0.45, 0.75], ...
    DisplayName="woShield");
hold(topAxes, "on");
loglog(topAxes, frequencyHz, wiAsdVPerSqrtHz, ...
    LineWidth=1.8, Color=[0.85, 0.325, 0.098], ...
    DisplayName="wiShield");
hold(topAxes, "off");
grid(topAxes, "on");
xlim(topAxes, [1, 25e3]);
ylabel(topAxes, "ASD (V/\surdHz)");
title(topAxes, "20-run 1/12-octave PSD averages");
legend(topAxes, Location="best", Interpreter="none");

bottomAxes = nexttile(layout);
semilogx(bottomAxes, frequencyHz, wiVsWoDb, ...
    Color=[0.3, 0.3, 0.3], LineWidth=1.5);
hold(bottomAxes, "on");
yline(bottomAxes, 0, "k--", HandleVisibility="off");
hold(bottomAxes, "off");
grid(bottomAxes, "on");
xlim(bottomAxes, [1, 25e3]);
xlabel(bottomAxes, "Frequency (Hz)");
ylabel(bottomAxes, "wiShield / woShield (dB)");
title(bottomAxes, "Positive values mean higher noise with the shield");

title(layout, "Shielding comparison using identical FFT processing");
savefig(comparisonFigure, fullfile(outputFolder, ...
    "Shielding_Comparison.fig"));
exportgraphics(comparisonFigure, fullfile(outputFolder, ...
    "Shielding_Comparison.png"), Resolution=240);

fprintf("Shielding comparison saved under %s\n", outputFolder);
disp(keyMetricComparison);

function value = centeredFractionalOctaveAsd( ...
        frequencyHz, psd, centerHz, bandsPerOctave)
frequencyStepHz = median(diff(frequencyHz));
lowHz = centerHz*2^(-1/(2*bandsPerOctave));
highHz = centerHz*2^(1/(2*bandsPerOctave));
binLowHz = frequencyHz-frequencyStepHz/2;
binHighHz = frequencyHz+frequencyStepHz/2;
overlapHz = max(0, min(binHighHz, highHz)-max(binLowHz, lowHz));
use = overlapHz > 0 & isfinite(psd) & psd >= 0;
assert(any(use), "No FFT bins are available around %.9g Hz.", centerHz);
averagePsd = sum(psd(use).*overlapHz(use))/sum(overlapHz(use));
value = sqrt(averagePsd);
end

function value = integrateNoise(frequencyHz, psd, lowHz, highHz)
use = frequencyHz >= lowHz & frequencyHz <= highHz;
frequencyStepHz = median(diff(frequencyHz));
value = sqrt(sum(psd(use))*frequencyStepHz);
end

function value = peakAsdInBand(frequencyHz, asd, lowHz, highHz)
use = frequencyHz >= lowHz & frequencyHz <= highHz;
value = max(asd(use));
end
