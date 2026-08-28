%% Analyze the 20 wiShield InstrumentStudio TDMS noise captures
% This wrapper deliberately calls the same reviewed analysis implementation
% used for the woShield data set, while directing all input and output to
% this folder.  Run this file whenever the wiShield data need re-analysis.

clearvars;
close all;
clc;

thisScriptPath = string(mfilename("fullpath"));
assert(strlength(thisScriptPath) > 0, ...
    "Run this file as a MATLAB script so its data folder can be resolved.");
dataFolderOverride = string(fileparts(thisScriptPath));

sharedAnalysisScript = fullfile(dataFolderOverride, "..", ...
    "Unicorn_CSA_RevA-COB_woShiled_20260828", ...
    "analyze_20run_time_only_noise.m");
assert(isfile(sharedAnalysisScript), ...
    "Shared analysis script was not found: %s", sharedAnalysisScript);

run(sharedAnalysisScript);
