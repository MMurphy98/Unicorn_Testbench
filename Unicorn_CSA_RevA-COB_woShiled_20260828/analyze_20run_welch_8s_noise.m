%% Re-analyze the 20 woShield captures with 8 s Welch averaging
% This wrapper preserves the legacy 22 s whole-record outputs and writes
% the Welch result under analysis_results/welch_8s_50pct.

clearvars;
close all;
clc;

thisScriptPath = string(mfilename("fullpath"));
assert(strlength(thisScriptPath) > 0, ...
    "Run this file as a MATLAB script so its data folder can be resolved.");
dataFolderOverride = string(fileparts(thisScriptPath));
analysisProfileOverride = "welch_8s_50pct";

sharedAnalysisScript = fullfile(dataFolderOverride, ...
    "analyze_20run_time_only_noise.m");
assert(isfile(sharedAnalysisScript), ...
    "Shared analysis script was not found: %s", sharedAnalysisScript);

run(sharedAnalysisScript);
