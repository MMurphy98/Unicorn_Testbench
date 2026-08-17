function [outputPaths, comparison] = replayProcessedComparison( ...
        processedDataPath, outputDir)
%REPLAYPROCESSEDCOMPARISON Regenerate artifacts without raw waveforms.

arguments
    processedDataPath (1, 1) string
    outputDir (1, 1) string
end

if ~isfile(processedDataPath)
    error("opa189:MissingProcessedData", ...
        "Processed OPA189 data does not exist: %s", processedDataPath);
end

try
    storedVariables = whos("-file", processedDataPath);
    storedVariableNames = string({storedVariables.name});
    if ~ismember("comparison", storedVariableNames)
        error("opa189:InvalidProcessedData", ...
            "Processed OPA189 data must contain a comparison struct.");
    end
    loadedData = load(processedDataPath, "comparison");
catch exception
    if strcmp(exception.identifier, "opa189:InvalidProcessedData")
        rethrow(exception);
    end
    error("opa189:InvalidProcessedData", ...
        "Could not load processed OPA189 data %s: %s", ...
        processedDataPath, exception.message);
end

comparison = loadedData.comparison;
validateProcessedComparison(comparison);
outputPaths = writeComparisonArtifacts(comparison, outputDir);
end

function validateProcessedComparison(comparison)
requiredFields = { ...
    'conditionLabels', 'results', 'summaryTable', 'runSummaryTable'};
if ~isstruct(comparison) || ~isscalar(comparison) || ...
        ~all(isfield(comparison, requiredFields))
    error("opa189:InvalidProcessedData", ...
        "The comparison struct is incomplete.");
end
if numel(comparison.conditionLabels) ~= 4 || ...
        ~isstruct(comparison.results) || numel(comparison.results) ~= 4
    error("opa189:InvalidProcessedData", ...
        "Processed OPA189 data must contain exactly four conditions.");
end
if ~istable(comparison.summaryTable) || ...
        ~istable(comparison.runSummaryTable)
    error("opa189:InvalidProcessedData", ...
        "Processed OPA189 summaries must be MATLAB tables.");
end

requiredResultFields = {'frequencyHz', 'inputAsdVrtHz'};
if ~all(isfield(comparison.results, requiredResultFields))
    error("opa189:InvalidProcessedData", ...
        "Each processed condition must contain frequency and input ASD.");
end

referenceFrequency = comparison.results(1).frequencyHz(:);
if isempty(referenceFrequency) || any(~isfinite(referenceFrequency)) || ...
        any(referenceFrequency <= 0) || any(diff(referenceFrequency) <= 0)
    error("opa189:InvalidProcessedData", ...
        "The processed frequency grid must be finite and increasing.");
end
for conditionIndex = 1:4
    frequencyHz = comparison.results(conditionIndex).frequencyHz(:);
    inputAsdVrtHz = comparison.results(conditionIndex).inputAsdVrtHz(:);
    if ~isequal(frequencyHz, referenceFrequency) || ...
            numel(inputAsdVrtHz) ~= numel(referenceFrequency) || ...
            any(~isfinite(inputAsdVrtHz)) || any(inputAsdVrtHz < 0)
        error("opa189:InvalidProcessedData", ...
            "Processed conditions must share one valid frequency grid.");
    end
end
end
