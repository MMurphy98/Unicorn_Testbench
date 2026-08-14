function [outputPaths, comparison] = runOpa189NoiseAnalysis( ...
        formalDataDir, outputDir)
%RUNOPA189NOISEANALYSIS Run the formal four-condition OPA189 pipeline.

arguments
    formalDataDir (1, 1) string = defaultFormalDataDir()
    outputDir (1, 1) string = defaultOutputDir()
end

repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
sourceDir = fullfile(repoRoot, "matlab", "src");
addpath(sourceDir);
cleanup = onCleanup(@() rmpath(sourceDir)); %#ok<NASGU>

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

function formalDataDir = defaultFormalDataDir()
repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
formalDataDir = string(fullfile( ...
    repoRoot, "data", "raw", "opa189", "formal_test"));
end

function outputDir = defaultOutputDir()
repoRoot = fileparts(fileparts(fileparts(mfilename("fullpath"))));
outputDir = string(fullfile(repoRoot, "results", "opa189"));
end
