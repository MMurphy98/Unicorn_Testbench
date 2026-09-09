%% Compare wiShield and woShield using the saved 8 s Welch results

clearvars;
close all;
clc;

thisScriptPath = string(mfilename("fullpath"));
assert(strlength(thisScriptPath) > 0, ...
    "Run this file as a MATLAB script so its folder can be resolved.");
analysisProfileOverride = "welch_8s_50pct";
comparisonScript = fullfile(fileparts(thisScriptPath), ...
    "compare_wi_vs_wo_noise.m");
assert(isfile(comparisonScript), ...
    "Comparison script was not found: %s", comparisonScript);

run(comparisonScript);
