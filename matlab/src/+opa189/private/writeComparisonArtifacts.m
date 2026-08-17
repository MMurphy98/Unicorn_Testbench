function outputPaths = writeComparisonArtifacts(comparison, outputDir)
%WRITECOMPARISONARTIFACTS Save tables, MAT data, and approved figures.

arguments
    comparison (1, 1) struct
    outputDir (1, 1) string
end

if ~isfolder(outputDir)
    mkdir(outputDir);
end

outputPaths = struct;
outputPaths.dataPath = fullfile( ...
    outputDir, "opa189_four_condition_analysis.mat");
outputPaths.summaryPath = fullfile( ...
    outputDir, "opa189_four_condition_summary.csv");
outputPaths.runSummaryPath = fullfile( ...
    outputDir, "opa189_four_condition_run_summary.csv");
outputPaths.fourConditionFigurePath = fullfile(outputDir, ...
    "opa189_four_condition_0p1_to_100hz.png");
outputPaths.shieldedFigurePath = fullfile(outputDir, ...
    "opa189_with_shield_voltage_comparison_0p1_to_100hz.png");

save(outputPaths.dataPath, "comparison");
writetable(comparison.summaryTable, outputPaths.summaryPath);
writetable(comparison.runSummaryTable, outputPaths.runSummaryPath);
exportComparisonFigures(comparison, outputPaths);
end
