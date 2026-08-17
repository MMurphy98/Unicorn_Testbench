classdef opa189ProcessedReplayTest < matlab.unittest.TestCase
    %OPA189PROCESSEDREPLAYTEST Tests offline replay without raw waveforms.

    properties
        RepoRoot (1, 1) string
        ProcessedDataPath (1, 1) string
        OutputDir (1, 1) string
    end

    methods (TestClassSetup)
        function addPublicPaths(testCase)
            testDir = fileparts(mfilename("fullpath"));
            matlabDir = fileparts(testDir);
            testCase.RepoRoot = string(fileparts(matlabDir));
            testCase.ProcessedDataPath = fullfile(testCase.RepoRoot, ...
                "data", "processed", "opa189", "formal_test", ...
                "opa189_four_condition_analysis.mat");
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "src"), IncludingSubfolders=true));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "scripts")));
        end
    end

    methods (TestMethodSetup)
        function createOutputDirectory(testCase)
            testCase.OutputDir = string(tempname);
            mkdir(testCase.OutputDir);
            testCase.addTeardown(@() rmdir(testCase.OutputDir, "s"));
        end
    end

    methods (Test)
        function testReplayWritesAllArtifacts(testCase)
            [outputPaths, comparison] = ...
                opa189.replayProcessedComparison( ...
                testCase.ProcessedDataPath, testCase.OutputDir);

            artifactPaths = comparisonArtifactPaths(outputPaths);
            testCase.verifyTrue(all(isfile(artifactPaths)));
            testCase.verifyEqual(numel(comparison.results), 4);
            testCase.verifyEqual( ...
                comparison.results(1).frequencyResolutionHz, ...
                0.1, AbsTol=1e-12);
            testCase.verifyEqual( ...
                comparison.results(1).frequencyHz(1), ...
                0.1, AbsTol=1e-12);
            testCase.verifyNumElements( ...
                comparison.results(1).frequencyHz, 1000);
        end

        function testCommittedDataDoesNotExposeLocalPaths(testCase)
            [~, comparison] = opa189.replayProcessedComparison( ...
                testCase.ProcessedDataPath, testCase.OutputDir);
            storedPaths = collectStoredPaths(comparison);
            redactedPath = ...
                "[raw waveform omitted; see data/raw/README.md]";

            testCase.verifyEqual(width(comparison.runSummaryTable), 12);
            testCase.verifyEqual( ...
                storedPaths, repmat(redactedPath, size(storedPaths)));
        end

        function testTopLevelEntryFallsBackWithoutRawData(testCase)
            defaultRawDataDir = fullfile(testCase.RepoRoot, ...
                "data", "raw", "opa189", "formal_test");

            outputPaths = runOpa189NoiseAnalysis( ...
                defaultRawDataDir, testCase.OutputDir);

            artifactPaths = comparisonArtifactPaths(outputPaths);
            testCase.verifyFalse(isfolder(defaultRawDataDir));
            testCase.verifyTrue(all(isfile(artifactPaths)));
        end

        function testMissingProcessedDataErrors(testCase)
            missingPath = fullfile(testCase.OutputDir, "missing.mat");
            action = @() opa189.replayProcessedComparison( ...
                missingPath, testCase.OutputDir);

            testCase.verifyError(action, "opa189:MissingProcessedData");
        end

        function testMalformedProcessedDataErrors(testCase)
            malformedPath = fullfile(testCase.OutputDir, "malformed.mat");
            invalidPayload = 42;
            save(malformedPath, "invalidPayload");
            action = @() opa189.replayProcessedComparison( ...
                malformedPath, testCase.OutputDir);

            testCase.verifyError(action, "opa189:InvalidProcessedData");
        end
    end
end

function paths = comparisonArtifactPaths(outputPaths)
paths = [ ...
    outputPaths.dataPath; ...
    outputPaths.summaryPath; ...
    outputPaths.runSummaryPath; ...
    outputPaths.fourConditionFigurePath; ...
    outputPaths.shieldedFigurePath];
end

function paths = collectStoredPaths(comparison)
conditionSourcePaths = vertcat(comparison.results.sourcePaths);
perRunResults = vertcat(comparison.results.perRunResults);
paths = [ ...
    comparison.conditionDirs; ...
    comparison.summaryTable.ConditionDirectory; ...
    comparison.runSummaryTable.sourcePath; ...
    string({comparison.results.sourcePath}).'; ...
    conditionSourcePaths; ...
    string({perRunResults.sourcePath}).'];
end
