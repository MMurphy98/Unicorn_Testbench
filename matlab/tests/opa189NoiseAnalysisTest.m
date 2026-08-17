classdef opa189NoiseAnalysisTest < matlab.unittest.TestCase
    %OPA189NOISEANALYSISTEST Tests the formal OPA189 Welch pipeline.

    properties
        WorkingDir (1, 1) string
        FormalDataDir (1, 1) string
        OutputDir (1, 1) string
        Config (1, 1) struct
    end

    methods (TestClassSetup)
        function addSourceToPath(testCase)
            testDir = fileparts(mfilename("fullpath"));
            matlabDir = fileparts(testDir);
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "src"), IncludingSubfolders=true));
        end
    end

    methods (TestMethodSetup)
        function createSyntheticDataset(testCase)
            testCase.WorkingDir = string(tempname);
            mkdir(testCase.WorkingDir);
            testCase.addTeardown(@() rmdir(testCase.WorkingDir, "s"));
            testCase.FormalDataDir = fullfile( ...
                testCase.WorkingDir, "formal_test");
            testCase.OutputDir = fullfile(testCase.WorkingDir, "results");
            testCase.Config = testConfig();
            writeFormalDataset(testCase.FormalDataDir, testCase.Config);
        end
    end

    methods (Test)
        function testWaveformWelchMetadata(testCase)
            csvPath = firstWaveformPath(testCase.FormalDataDir);

            result = opa189.analyzeWaveform(csvPath, testCase.Config);

            testCase.verifyEqual(result.sampleRateHz, 1000, RelTol=1e-9);
            testCase.verifyEqual(result.welchSegmentCount, 2);
            testCase.verifyEqual( ...
                result.frequencyResolutionHz, 0.1, AbsTol=1e-12);
            testCase.verifyEqual( ...
                result.frequencyHz(1), 0.1, AbsTol=1e-9);
            testCase.verifyEqual( ...
                result.frequencyHz(end), 100, AbsTol=1e-9);
            testCase.verifyNumElements(result.frequencyHz, 1000);
            testCase.verifyTrue(all(isfinite(result.inputPsdV2PerHz)));
        end

        function testFormalIntegrationIncludesNominalLowerEdge(testCase)
            [conditionDirs, labels] = formalInputs(testCase.FormalDataDir);

            [~, comparison] = opa189.processFormalComparison( ...
                conditionDirs, labels, testCase.OutputDir, testCase.Config);
            result = comparison.results(1);
            expectedNoiseVrms = sqrt(trapz( ...
                result.frequencyHz(1:100), ...
                result.inputPsdV2PerHz(1:100)));

            testCase.verifyEqual( ...
                result.frequencyHz(1), 0.1, AbsTol=1e-9);
            testCase.verifyEqual( ...
                result.frequencyHz(100), 10, AbsTol=1e-9);
            testCase.verifyEqual( ...
                result.integratedNoise0p1To10Vrms, expectedNoiseVrms, ...
                RelTol=1e-12);
        end

        function testFormalComparisonAveragesPsd(testCase)
            [conditionDirs, labels] = formalInputs(testCase.FormalDataDir);

            [~, comparison] = opa189.processFormalComparison( ...
                conditionDirs, labels, testCase.OutputDir, testCase.Config);
            perRunPsd = cat(2, ...
                comparison.results(1).perRunResults.inputPsdV2PerHz);

            testCase.verifyEqual([comparison.results.runCount].', ...
                repmat(10, 4, 1));
            testCase.verifyEqual( ...
                comparison.results(1).inputPsdV2PerHz, ...
                mean(perRunPsd, 2), AbsTol=1e-24);
            testCase.verifySize(comparison.runSummaryTable, [40, 12]);
        end

        function testFormalComparisonWritesOutputs(testCase)
            [conditionDirs, labels] = formalInputs(testCase.FormalDataDir);

            outputPaths = opa189.processFormalComparison( ...
                conditionDirs, labels, testCase.OutputDir, testCase.Config);

            testCase.verifyTrue(isfile(outputPaths.dataPath));
            testCase.verifyTrue(isfile(outputPaths.summaryPath));
            testCase.verifyTrue(isfile(outputPaths.runSummaryPath));
            testCase.verifyTrue(isfile(outputPaths.fourConditionFigurePath));
            testCase.verifyTrue(isfile(outputPaths.shieldedFigurePath));
        end

        function testMissingRunFolderErrors(testCase)
            [conditionDirs, labels] = formalInputs(testCase.FormalDataDir);
            rmdir(fullfile(conditionDirs(1), "run_10"), "s");

            action = @() opa189.processFormalComparison( ...
                conditionDirs, labels, testCase.OutputDir, testCase.Config);

            testCase.verifyError(action, "opa189:InvalidFormalRunFolders");
        end
    end
end

function cfg = testConfig()
cfg = opa189.defaultConfig();
cfg.expectedSampleRateHz = 1000;
cfg.noiseGain = 10;
end

function [conditionDirs, labels] = formalInputs(formalDataDir)
conditionNames = [ ...
    "pm3v_no_shield"; ...
    "pm3v_with_shield"; ...
    "pm18v_no_shield"; ...
    "pm18v_with_shield"];
conditionDirs = fullfile(formalDataDir, conditionNames);
labels = ["3V no shield"; "3V shield"; "18V no shield"; "18V shield"];
end

function csvPath = firstWaveformPath(formalDataDir)
csvPath = fullfile(formalDataDir, ...
    "pm3v_no_shield", "run_01", "Synthetic Waveform Data.csv");
end

function writeFormalDataset(formalDataDir, cfg)
[conditionDirs, ~] = formalInputs(formalDataDir);
originalState = rng;
cleanup = onCleanup(@() rng(originalState));
rng(42, "twister");
for conditionIndex = 1:4
    for runIndex = 1:10
        runDir = fullfile(conditionDirs(conditionIndex), ...
            sprintf("run_%02d", runIndex));
        mkdir(runDir);
        csvPath = fullfile(runDir, "Synthetic Waveform Data.csv");
        writeWaveform(csvPath, cfg, conditionIndex, runIndex);
    end
end
end

function writeWaveform(csvPath, cfg, conditionIndex, runIndex)
sampleCount = round(19.54872*cfg.expectedSampleRateHz);
sampleIntervalS = (1/cfg.expectedSampleRateHz)*(1 + 1e-12);
timeS = (0:sampleCount-1).'*sampleIntervalS;
noiseV = 40e-9*randn(sampleCount, 1);
mainsV = (0.8e-6 + conditionIndex*0.1e-6)*sin(2*pi*50*timeS);
lowFrequencyV = runIndex*1e-9*sin(2*pi*timeS);
voltageV = noiseV + mainsV + lowFrequencyV;

fileId = fopen(csvPath, "w");
if fileId < 0
    error("opa189Test:CannotCreateCsv", ...
        "Cannot create synthetic waveform CSV.");
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, "Meta data\n");
fprintf(fileId, "Physical channel,Start Time,Sample Interval,Sample Count\n");
fprintf(fileId, "Channel 0 (PXI1Slot2/0),0,%.17g,%d\n\n", ...
    sampleIntervalS, sampleCount);
fprintf(fileId, "Data\n");
fprintf(fileId, "Channel 0 (PXI1Slot2/0)\n");
fprintf(fileId, "%.12g\n", voltageV);
end
