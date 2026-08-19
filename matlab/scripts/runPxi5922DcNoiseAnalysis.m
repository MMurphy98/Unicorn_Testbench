function [averageAsdVrtHz, frequencyHz, outputPaths] = ...
        runPxi5922DcNoiseAnalysis(dataDir, outputDir)
%RUNPXI5922DCNOISEANALYSIS Analyze the ten DC-coupled PXI-5922 captures.
%   [ASD, F, PATHS] = RUNPXI5922DCNOISEANALYSIS() applies the same
%   50 kS/s, first-900,000-point, ten-PSD-average method as the AC-coupled
%   analysis. It writes CSV, MAT, PNG, and MATLAB FIG outputs below the
%   run_02 results directory.
%
%   Optional DATA_DIR and OUTPUT_DIR arguments override the repository
%   defaults.

arguments
    dataDir (1, 1) string = defaultDcDataDir()
    outputDir (1, 1) string = defaultDcOutputDir()
end

fileStem = "Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_dc";
[averageAsdVrtHz, frequencyHz, outputPaths] = ...
    runPxi5922NoiseAnalysis( ...
    dataDir, outputDir, fileStem, "DC coupling");
end

function path = defaultDcDataDir()
path = string(fullfile(repoRoot(), "data", "raw", "PXI-5922", ...
    "Capture_50kS_ 2026-08-19_Unicorn_COB_RevA_run_02"));
end

function path = defaultDcOutputDir()
path = string(fullfile(repoRoot(), "results", "PXI-5922", ...
    "2026-08-19_Unicorn_COB_RevA_run_02"));
end

function path = repoRoot()
path = fileparts(fileparts(fileparts(mfilename("fullpath"))));
end
