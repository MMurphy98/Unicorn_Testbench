%% Re-analyze the 20 woShield, 1.2x-current captures with 8 s Welch
% The Welch result is written under analysis_results/welch_8s_50pct and
% does not overwrite the archived 22 s whole-record result.

clearvars;
close all;
clc;

thisScriptPath = string(mfilename("fullpath"));
assert(strlength(thisScriptPath) > 0, ...
    "Run this file as a MATLAB script so its data folder can be resolved.");
analysisProfileOverride = "welch_8s_50pct";
analysisScript = fullfile(fileparts(thisScriptPath), ...
    "analyze_20run_time_only_noise.m");
assert(isfile(analysisScript), ...
    "Analysis wrapper was not found: %s", analysisScript);

run(analysisScript);
