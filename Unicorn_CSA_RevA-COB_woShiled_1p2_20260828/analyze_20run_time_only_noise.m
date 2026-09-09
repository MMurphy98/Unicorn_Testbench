%% Analyze the 20 woShield, 1.2x-current TDMS noise captures
% This wrapper uses the same reviewed implementation as the nominal-current
% woShield data set. By default it preserves the 22 s whole-record result.

if exist("analysisProfileOverride", "var")
    analysisProfileOverride = string(analysisProfileOverride);
else
    analysisProfileOverride = "whole_record_22s";
end
clearvars -except analysisProfileOverride;
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
