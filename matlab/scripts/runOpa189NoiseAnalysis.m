function [outputPaths, comparison] = runOpa189NoiseAnalysis( ...
        formalDataDir, outputDir)
%RUNOPA189NOISEANALYSIS Run the formal four-condition OPA189 pipeline.

arguments
    formalDataDir (1, 1) string = defaultFormalDataDir()
    outputDir (1, 1) string = defaultOutputDir()
end

repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
sourceDir = fullfile(repoRoot, "matlab", "src");
pathCleanup = addSourcePathWhenMissing(sourceDir); %#ok<NASGU>

if ~isfolder(formalDataDir)
    if isDefaultFormalDataDir(formalDataDir)
        processedDataPath = defaultProcessedDataPath();
        fprintf("Raw OPA189 waveforms are not present. " + ...
            "Replaying committed processed spectral data:\n%s\n", ...
            processedDataPath);
        [outputPaths, comparison] = opa189.replayProcessedComparison( ...
            processedDataPath, outputDir);
        return
    end
    error("opa189:MissingFormalDataDirectory", ...
        "Formal OPA189 data directory does not exist: %s", formalDataDir);
end

conditionDirs = fullfile(formalDataDir, [ ...
    "pm3v_no_shield"; ...
    "pm3v_with_shield"; ...
    "pm18v_no_shield"; ...
    "pm18v_with_shield"]);
conditionLabels = [ ...
    "±3 V，无屏蔽罩"; ...
    "±3 V，有屏蔽罩"; ...
    "±18 V，无屏蔽罩"; ...
    "±18 V，有屏蔽罩"];

[outputPaths, comparison] = opa189.processFormalComparison( ...
    conditionDirs, conditionLabels, outputDir);
end

function tf = isDefaultFormalDataDir(formalDataDir)
defaultPath = char(defaultFormalDataDir());
candidatePath = char(formalDataDir);
if ispc
    tf = strcmpi(candidatePath, defaultPath);
else
    tf = strcmp(candidatePath, defaultPath);
end
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

function formalDataDir = defaultFormalDataDir()
repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
formalDataDir = string(fullfile( ...
    repoRoot, "data", "raw", "opa189", "formal_test"));
end

function processedDataPath = defaultProcessedDataPath()
repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
processedDataPath = string(fullfile(repoRoot, "data", "processed", ...
    "opa189", "formal_test", "opa189_four_condition_analysis.mat"));
end

function outputDir = defaultOutputDir()
repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
outputDir = string(fullfile(repoRoot, "results", "opa189"));
end
