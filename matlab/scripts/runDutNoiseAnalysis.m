function [result, outputPaths] = runDutNoiseAnalysis( ...
        dataRoot, outputDir, processedDir, cobNumbers, cfg)
%RUNDUTNOISEANALYSIS Analyze DUT noise versus COB and bias current.
%   RESULT = RUNDUTNOISEANALYSIS() processes COB 1 through 3 from the
%   sibling Chip_Benchmark data directory. Each condition must contain ten
%   run_XX folders. The first 900,000 points of each 50 kS/s waveform are
%   mean-removed and converted to a periodic-Hann single-sided PSD. Ten
%   PSDs are averaged before taking the square root, then divided by the
%   1001 voltage gain to obtain input-referred ASD.
%
%   Full-resolution generated files are written below results/ and remain
%   untracked. Compact plot spectra, summaries, and PNG figures are written
%   below data/processed/ for review and later reproduction without raw
%   waveform CSV files.

arguments
    dataRoot (1, 1) string = defaultDataRoot()
    outputDir (1, 1) string = defaultOutputDir()
    processedDir (1, 1) string = defaultProcessedDir()
    cobNumbers (1, :) double {mustBeInteger, mustBePositive} = 1:3
    cfg (1, 1) struct = defaultConfig()
end

sourceDir = fullfile(repoRoot(), "matlab", "src");
pathCleanup = addSourcePathWhenMissing(sourceDir); %#ok<NASGU>

fprintf("DUT raw data: %s\n", dataRoot);
fprintf("COBs: %s\n", join(string(cobNumbers), ", "));
result = dut.processCampaign( ...
    dataRoot, outputDir, processedDir, cobNumbers, cfg);
outputPaths = result.outputPaths;

fprintf("Full local analysis: %s\n", outputPaths.fullAnalysisMat);
fprintf("Compact processed data: %s\n", outputPaths.plotDataMat);
fprintf("By-COB figure: %s\n", outputPaths.byCobPng);
fprintf("By-bias figure: %s\n", outputPaths.byBiasPng);
end

function cfg = defaultConfig()
cfg = struct;
cfg.sampleRateHz = 50e3;
cfg.pointCount = 900000;
cfg.runCount = 10;
cfg.gain = 1001;
cfg.biasCurrentsMicroA = [1, 2, 4];
cfg.supplyLabel = "3V3";
cfg.gainLabel = "1001gain";
cfg.plotBinCount = 3000;
cfg.plotFrequencyLimitsHz = [0.1, 25e3];
end

function path = defaultDataRoot()
path = string(fullfile(fileparts(repoRoot()), ...
    "Chip_Benchmark", "data", "DUT_noise"));
end

function path = defaultOutputDir()
path = string(fullfile(repoRoot(), "results", "DUT_noise", ...
    "3V3_1001gain_COB1-3"));
end

function path = defaultProcessedDir()
path = string(fullfile(repoRoot(), "data", "processed", ...
    "dut_noise", "3V3_1001gain_COB1-3"));
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

function path = repoRoot()
path = fileparts(fileparts(fileparts(mfilename("fullpath"))));
end
