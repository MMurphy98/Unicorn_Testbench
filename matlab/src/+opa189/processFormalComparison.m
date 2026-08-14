function [outputPaths, comparison] = processFormalComparison( ...
        conditionDirs, conditionLabels, outputDir, cfg)
%PROCESSFORMALCOMPARISON Average ten Welch PSDs for four conditions.

arguments
    conditionDirs (4, 1) string
    conditionLabels (4, 1) string
    outputDir (1, 1) string
    cfg (1, 1) struct = opa189.defaultConfig()
end

if any(strlength(strip(conditionLabels)) == 0)
    error("opa189:EmptyConditionLabel", ...
        "Formal condition labels must not be empty.");
end
if ~isfolder(outputDir)
    mkdir(outputDir);
end

conditionResults = cell(4, 1);
for conditionIndex = 1:4
    conditionResults{conditionIndex} = analyzeCondition( ...
        conditionDirs(conditionIndex), cfg);
    if conditionIndex > 1
        validateFrequencyGrid(conditionResults{1}, ...
            conditionResults{conditionIndex});
    end
end
results = vertcat(conditionResults{:});

comparison = struct;
comparison.conditionLabels = conditionLabels;
comparison.conditionDirs = conditionDirs;
comparison.results = results;
comparison.summaryTable = buildConditionSummary( ...
    conditionLabels, conditionDirs, results);
comparison.runSummaryTable = buildRunSummary(conditionLabels, results);
comparison.analysisMethod = ...
    "Each raw waveform is linearly detrended and analyzed with Welch " + ...
    "PSD (10 s periodic Hann, 50% overlap). Ten run PSDs are averaged " + ...
    "along dimension 2; ASD is the square root of the mean PSD.";

outputPaths = struct;
outputPaths.dataPath = fullfile( ...
    outputDir, "opa189_four_condition_analysis.mat");
outputPaths.summaryPath = fullfile( ...
    outputDir, "opa189_four_condition_summary.csv");
outputPaths.runSummaryPath = fullfile( ...
    outputDir, "opa189_four_condition_run_summary.csv");
outputPaths.fourConditionFigurePath = fullfile(outputDir, ...
    "opa189_four_condition_0p1_to_100hz.png");
outputPaths.shieldedFigurePath = fullfile(outputDir, ...
    "opa189_with_shield_voltage_comparison_0p1_to_100hz.png");

save(outputPaths.dataPath, "comparison");
writetable(comparison.summaryTable, outputPaths.summaryPath);
writetable(comparison.runSummaryTable, outputPaths.runSummaryPath);
exportComparisonFigures(comparison, outputPaths);
end

function result = analyzeCondition(conditionDir, cfg)
if ~isfolder(conditionDir)
    error("opa189:MissingConditionDirectory", ...
        "Formal condition directory does not exist: %s", conditionDir);
end

expectedRunNames = string(compose("run_%02d", (1:10).'));
runEntries = dir(fullfile(conditionDir, "run_*"));
runEntries = runEntries([runEntries.isdir]);
runNames = sort(string({runEntries.name}).');
if ~isequal(runNames, expectedRunNames)
    error("opa189:InvalidFormalRunFolders", ...
        "Condition %s must contain exactly run_01 through run_10.", ...
        conditionDir);
end

firstResult = analyzeRun(conditionDir, expectedRunNames(1), cfg);
perRunResults = repmat(firstResult, 10, 1);
for runIndex = 2:10
    runResult = analyzeRun( ...
        conditionDir, expectedRunNames(runIndex), cfg);
    validateFrequencyGrid(perRunResults(1), runResult);
    perRunResults(runIndex) = runResult;
end

inputPsdPerRun = cat(2, perRunResults.inputPsdV2PerHz);
outputPsdPerRun = cat(2, perRunResults.outputPsdV2PerHz);
meanInputPsd = mean(inputPsdPerRun, 2);
meanOutputPsd = mean(outputPsdPerRun, 2);
frequencyHz = perRunResults(1).frequencyHz;
quietMask = frequencyHz >= cfg.quietBandHz(1) & ...
    frequencyHz <= cfg.quietBandHz(2);
[~, mainsIndex] = min(abs(frequencyHz-50));

result = perRunResults(1);
result.sourcePath = char(conditionDir);
result.sourcePaths = string({perRunResults.sourcePath}).';
result.runCount = numel(perRunResults);
result.totalWelchSegmentCount = sum([perRunResults.welchSegmentCount]);
result.perRunResults = perRunResults;
result.outputPsdV2PerHz = meanOutputPsd;
result.inputPsdV2PerHz = meanInputPsd;
result.outputAsdVrtHz = sqrt(max(meanOutputPsd, 0));
result.inputAsdVrtHz = sqrt(max(meanInputPsd, 0));
result.quietBandMedianInputAsdVrtHz = median( ...
    result.inputAsdVrtHz(quietMask));
result.mains50HzInputAsdVrtHz = result.inputAsdVrtHz(mainsIndex);
result.integratedNoise0p1To10Vrms = integratePsdBand( ...
    frequencyHz, meanInputPsd, cfg.integrationBandsHz(1, :));
result.integratedNoise0p1To100Vrms = integratePsdBand( ...
    frequencyHz, meanInputPsd, cfg.integrationBandsHz(2, :));
result.analysisMethod = ...
    "Mean of ten per-run Welch PSDs; ASD is sqrt(mean PSD).";
end

function runResult = analyzeRun(conditionDir, runName, cfg)
runDir = fullfile(conditionDir, runName);
waveformFiles = dir(fullfile(runDir, "*Waveform Data.csv"));
if numel(waveformFiles) ~= 1
    error("opa189:InvalidWaveformFileCount", ...
        "%s must contain exactly one Waveform Data.csv file.", runDir);
end
waveformPath = fullfile(waveformFiles(1).folder, waveformFiles(1).name);
runResult = opa189.analyzeWaveform(string(waveformPath), cfg);
end

function summaryTable = buildConditionSummary(labels, dirs, results)
runCount = reshape([results.runCount], [], 1);
samplesPerRun = reshape([results.recordSampleCount], [], 1);
sampleRateHz = reshape([results.sampleRateHz], [], 1);
recordDurationSPerRun = reshape([results.recordDurationS], [], 1);
welchSegmentsPerRun = reshape([results.welchSegmentCount], [], 1);
totalWelchSegmentCount = reshape( ...
    [results.totalWelchSegmentCount], [], 1);
frequencyResolutionHz = reshape( ...
    [results.frequencyResolutionHz], [], 1);
quietBandMedianInputAsdNVrtHz = reshape( ...
    [results.quietBandMedianInputAsdVrtHz], [], 1)*1e9;
mains50HzInputAsdNVrtHz = reshape( ...
    [results.mains50HzInputAsdVrtHz], [], 1)*1e9;
integratedNoise0p1To10NVrms = reshape( ...
    [results.integratedNoise0p1To10Vrms], [], 1)*1e9;
integratedNoise0p1To100NVrms = reshape( ...
    [results.integratedNoise0p1To100Vrms], [], 1)*1e9;

summaryTable = table(labels, dirs, runCount, samplesPerRun, ...
    sampleRateHz, recordDurationSPerRun, welchSegmentsPerRun, ...
    totalWelchSegmentCount, frequencyResolutionHz, ...
    quietBandMedianInputAsdNVrtHz, mains50HzInputAsdNVrtHz, ...
    integratedNoise0p1To10NVrms, integratedNoise0p1To100NVrms, ...
    VariableNames=[ ...
        "Condition", "ConditionDirectory", "RunCount", ...
        "SamplesPerRun", "SampleRateHz", "RecordDurationSPerRun", ...
        "WelchSegmentsPerRun", "TotalWelchSegmentCount", ...
        "FrequencyResolutionHz", "QuietBandMedianInputAsdNVrtHz", ...
        "Mains50HzInputAsdNVrtHz", ...
        "IntegratedNoise0p1To10NVrms", ...
        "IntegratedNoise0p1To100NVrms"]);
end

function summaryTable = buildRunSummary(labels, results)
rowCount = 40;
condition = strings(rowCount, 1);
run = strings(rowCount, 1);
sourcePath = strings(rowCount, 1);
sampleCount = zeros(rowCount, 1);
sampleRateHz = zeros(rowCount, 1);
recordDurationS = zeros(rowCount, 1);
welchSegmentCount = zeros(rowCount, 1);
frequencyResolutionHz = zeros(rowCount, 1);
quietBandMedianInputAsdNVrtHz = zeros(rowCount, 1);
mains50HzInputAsdNVrtHz = zeros(rowCount, 1);
integratedNoise0p1To10NVrms = zeros(rowCount, 1);
integratedNoise0p1To100NVrms = zeros(rowCount, 1);

rowIndex = 0;
for conditionIndex = 1:4
    for runIndex = 1:10
        rowIndex = rowIndex + 1;
        runResult = results(conditionIndex).perRunResults(runIndex);
        condition(rowIndex) = labels(conditionIndex);
        run(rowIndex) = sprintf("run_%02d", runIndex);
        sourcePath(rowIndex) = string(runResult.sourcePath);
        sampleCount(rowIndex) = runResult.recordSampleCount;
        sampleRateHz(rowIndex) = runResult.sampleRateHz;
        recordDurationS(rowIndex) = runResult.recordDurationS;
        welchSegmentCount(rowIndex) = runResult.welchSegmentCount;
        frequencyResolutionHz(rowIndex) = runResult.frequencyResolutionHz;
        quietBandMedianInputAsdNVrtHz(rowIndex) = ...
            runResult.quietBandMedianInputAsdVrtHz*1e9;
        mains50HzInputAsdNVrtHz(rowIndex) = ...
            runResult.mains50HzInputAsdVrtHz*1e9;
        integratedNoise0p1To10NVrms(rowIndex) = ...
            runResult.integratedNoise0p1To10Vrms*1e9;
        integratedNoise0p1To100NVrms(rowIndex) = ...
            runResult.integratedNoise0p1To100Vrms*1e9;
    end
end

summaryTable = table(condition, run, sourcePath, sampleCount, ...
    sampleRateHz, recordDurationS, welchSegmentCount, ...
    frequencyResolutionHz, quietBandMedianInputAsdNVrtHz, ...
    mains50HzInputAsdNVrtHz, integratedNoise0p1To10NVrms, ...
    integratedNoise0p1To100NVrms);
end

function validateFrequencyGrid(reference, candidate)
if numel(reference.frequencyHz) ~= numel(candidate.frequencyHz)
    error("opa189:FrequencyGridMismatch", ...
        "All formal runs must use the same frequency grid.");
end
frequencyScale = max(1, max(abs(reference.frequencyHz)));
toleranceHz = 32*eps(frequencyScale);
if any(abs(reference.frequencyHz-candidate.frequencyHz) > toleranceHz)
    error("opa189:FrequencyGridMismatch", ...
        "All formal runs must use the same frequency grid.");
end
end

function noiseVrms = integratePsdBand(frequencyHz, psdV2PerHz, limitsHz)
take = frequencyHz >= limitsHz(1) & frequencyHz <= limitsHz(2);
if nnz(take) < 2
    error("opa189:MissingComparisonBand", ...
        "The Welch result does not contain the requested band.");
end
noiseVrms = sqrt(max(trapz(frequencyHz(take), psdV2PerHz(take)), 0));
end
