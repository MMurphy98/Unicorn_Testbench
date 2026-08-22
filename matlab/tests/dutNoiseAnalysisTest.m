classdef dutNoiseAnalysisTest < matlab.unittest.TestCase
    %DUTNOISEANALYSISTEST Tests the DUT campaign noise processor.

    methods (TestClassSetup)
        function addSourceToPath(testCase)
            testDir = fileparts(mfilename("fullpath"));
            matlabDir = fileparts(testDir);
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "src"), IncludingSubfolders=true));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "scripts")));
        end
    end

    methods (Test)
        function testAveragesPsdInPowerDomainAndRefersItToInput(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            dataRoot = fullfile(workDir, "raw");
            outputDir = fullfile(workDir, "results");
            processedDir = fullfile(workDir, "processed");
            createTwoRunCampaign(dataRoot, cfg);

            result = dut.processCampaign( ...
                dataRoot, outputDir, processedDir, 1, cfg);

            integratedInputNoiseV2 = trapz( ...
                result.frequencyHz, ...
                result.averageInputPsdV2PerHz(:, 1));
            expectedInputNoiseV2 = ((1^2/2) + (3^2/2))/2/cfg.gain^2;
            testCase.verifyEqual( ...
                integratedInputNoiseV2, expectedInputNoiseV2, ...
                RelTol=1e-10);
            testCase.verifyEqual(result.conditionKeys, "COB1_1uA");
            testCase.verifyEqual( ...
                result.runSummary.DcMeanOutputV, [0.1; 0.2], ...
                AbsTol=1e-12);
        end

        function testMissingRunErrorsBeforeProcessing(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            dataRoot = fullfile(workDir, "raw");
            createSingleRunCampaign(dataRoot, cfg, cfg.pointCount);

            action = @() dut.processCampaign( ...
                dataRoot, fullfile(workDir, "results"), ...
                fullfile(workDir, "processed"), 1, cfg);

            testCase.verifyError(action, "dut:MissingWaveformFile");
        end

        function testShortCaptureErrorsBeforeProcessing(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            cfg.runCount = 1;
            dataRoot = fullfile(workDir, "raw");
            createSingleRunCampaign(dataRoot, cfg, cfg.pointCount-1);

            action = @() dut.processCampaign( ...
                dataRoot, fullfile(workDir, "results"), ...
                fullfile(workDir, "processed"), 1, cfg);

            testCase.verifyError(action, "dut:InsufficientSamples");
        end

        function testExportsLocalAndProcessedArtifacts(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            dataRoot = fullfile(workDir, "raw");
            outputDir = fullfile(workDir, "results");
            processedDir = fullfile(workDir, "processed");
            createTwoRunCampaign(dataRoot, cfg);

            result = dut.processCampaign( ...
                dataRoot, outputDir, processedDir, 1, cfg);

            localArtifacts = [ ...
                result.outputPaths.fullAnalysisMat; ...
                result.outputPaths.fullSpectrumCsv; ...
                result.outputPaths.runSummaryCsv; ...
                result.outputPaths.conditionSummaryCsv];
            processedArtifacts = [ ...
                result.outputPaths.plotDataMat; ...
                result.outputPaths.plotSpectrumCsv; ...
                result.outputPaths.processedRunSummaryCsv; ...
                result.outputPaths.processedConditionSummaryCsv; ...
                result.outputPaths.byCobPng; ...
                result.outputPaths.byBiasPng];
            plotSpectrum = readtable( ...
                result.outputPaths.plotSpectrumCsv, TextType="string");
            localRunSummary = readtable( ...
                result.outputPaths.runSummaryCsv, TextType="string");
            processedRunSummary = readtable( ...
                result.outputPaths.processedRunSummaryCsv, ...
                TextType="string");
            byCobFigure = openfig( ...
                result.outputPaths.byCobFig, "invisible");
            testCase.addTeardown(@() close(byCobFigure));
            byBiasFigure = openfig( ...
                result.outputPaths.byBiasFig, "invisible");
            testCase.addTeardown(@() close(byBiasFigure));
            axesHandles = findall(byCobFigure, Type="axes");

            testCase.verifyTrue(all(isfile(localArtifacts)));
            testCase.verifyTrue(all(isfile(processedArtifacts)));
            testCase.verifyLessThanOrEqual( ...
                height(plotSpectrum), cfg.plotBinCount);
            testCase.verifyEqual( ...
                plotSpectrum.Properties.VariableNames, ...
                {'Frequency_Hz', ...
                'COB1_1uA_Input_ASD_nV_per_sqrtHz'});
            testCase.verifyTrue(all(contains( ...
                localRunSummary.SourcePath, "Synthetic")));
            testCase.verifyEqual(unique( ...
                processedRunSummary.SourcePath), ...
                "[raw waveform omitted; see data/raw/README.md]");
            testCase.verifyEqual( ...
                string({axesHandles.XScale}), ...
                repmat("log", 1, numel(axesHandles)));
            testCase.verifyEqual( ...
                string({axesHandles.YScale}), ...
                repmat("log", 1, numel(axesHandles)));
            testCase.verifyEqual( ...
                vertcat(axesHandles.Color), ...
                ones(numel(axesHandles), 3), AbsTol=1e-12);
            verifyOpa189References(testCase, byCobFigure);
            verifyOpa189References(testCase, byBiasFigure);
            verifySharedOutsideLegend(testCase, byCobFigure);
            verifySharedOutsideLegend(testCase, byBiasFigure);
        end

        function testTaskEntryProcessesExplicitCampaign(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            dataRoot = fullfile(workDir, "raw");
            createTwoRunCampaign(dataRoot, cfg);

            [result, outputPaths] = runDutNoiseAnalysis( ...
                dataRoot, fullfile(workDir, "results"), ...
                fullfile(workDir, "processed"), 1, cfg);

            testCase.verifyEqual(result.conditionKeys, "COB1_1uA");
            testCase.verifyTrue(isfile(outputPaths.plotDataMat));
        end

        function testUnexpectedSampleRateErrors(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            cfg.runCount = 1;
            sourceCfg = cfg;
            sourceCfg.sampleRateHz = 800;
            dataRoot = fullfile(workDir, "raw");
            createSingleRunCampaign( ...
                dataRoot, sourceCfg, sourceCfg.pointCount);

            action = @() dut.processCampaign( ...
                dataRoot, fullfile(workDir, "results"), ...
                fullfile(workDir, "processed"), 1, cfg);

            testCase.verifyError(action, "dut:UnexpectedSampleRate");
        end

        function testNonfiniteSamplesError(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            cfg.runCount = 1;
            dataRoot = fullfile(workDir, "raw");
            waveformV = zeros(cfg.pointCount, 1);
            waveformV(500) = NaN;
            writeRun(dataRoot, cfg, 1, waveformV);

            action = @() dut.processCampaign( ...
                dataRoot, fullfile(workDir, "results"), ...
                fullfile(workDir, "processed"), 1, cfg);

            testCase.verifyError(action, "dut:NonfiniteSamples");
        end

        function testProcessedDataReplaysFiguresWithoutRawCsv(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            cfg = syntheticConfig();
            dataRoot = fullfile(workDir, "raw");
            outputDir = fullfile(workDir, "results");
            processedDir = fullfile(workDir, "processed");
            createTwoRunCampaign(dataRoot, cfg);
            result = dut.processCampaign( ...
                dataRoot, outputDir, processedDir, 1, cfg);
            rmdir(dataRoot, "s");
            delete(result.outputPaths.byCobPng);
            delete(result.outputPaths.byBiasPng);

            replayPaths = dut.replayProcessedCampaign(processedDir);

            testCase.verifyTrue(isfile(replayPaths.byCobPng));
            testCase.verifyTrue(isfile(replayPaths.byBiasPng));
        end
    end
end

function verifyOpa189References(testCase, figureHandle)
axesHandles = findall(figureHandle, Type="axes");
referenceLines = findall(figureHandle, Type="constantline");
testCase.verifyNumElements(referenceLines, numel(axesHandles));
testCase.verifyEqual( ...
    [referenceLines.Value], repmat(5.2, 1, numel(axesHandles)), ...
    AbsTol=1e-12);
testCase.verifyEqual( ...
    string({referenceLines.DisplayName}), ...
    repmat("OPA189 typ.: 5.2 nV/sqrt(Hz) @ 1 kHz", ...
    1, numel(axesHandles)));
end

function verifySharedOutsideLegend(testCase, figureHandle)
legendHandles = findall(figureHandle, Type="legend");
testCase.verifyNumElements(legendHandles, 1);
testCase.verifyEqual(string(legendHandles.Orientation), "horizontal");
testCase.verifyEqual(string(legendHandles.Layout.Tile), "north");
end

function cfg = syntheticConfig()
cfg = struct;
cfg.sampleRateHz = 1000;
cfg.pointCount = 1000;
cfg.runCount = 2;
cfg.gain = 10;
cfg.biasCurrentsMicroA = 1;
cfg.supplyLabel = "3V3";
cfg.gainLabel = "1001gain";
cfg.plotBinCount = 64;
cfg.plotFrequencyLimitsHz = [1, 500];
end

function createTwoRunCampaign(dataRoot, cfg)
t = (0:cfg.pointCount-1)'/cfg.sampleRateHz;
firstWaveformV = 0.1 + sin(2*pi*100*t);
secondWaveformV = 0.2 + 3*sin(2*pi*100*t);
writeRun(dataRoot, cfg, 1, firstWaveformV);
writeRun(dataRoot, cfg, 2, secondWaveformV);
end

function createSingleRunCampaign(dataRoot, cfg, sampleCount)
t = (0:sampleCount-1)'/cfg.sampleRateHz;
waveformV = 0.1 + sin(2*pi*100*t);
writeRun(dataRoot, cfg, 1, waveformV);
end

function writeRun(dataRoot, cfg, runIndex, waveformV)
conditionDir = fullfile(dataRoot, sprintf( ...
    "NO.1_%s_%s_Ibias_1uA", cfg.supplyLabel, cfg.gainLabel));
runDir = fullfile(conditionDir, sprintf("run_%02d", runIndex));
mkdir(runDir);
csvPath = fullfile(runDir, "Synthetic Oscilloscope - Waveform Data.csv");
header = [ ...
    "Meta data"; ...
    "Physical channel,Start Time,Sample Interval,Sample Count"; ...
    sprintf("Channel 0 (PXI1Slot2/0),0,%.17g,%d", ...
    1/cfg.sampleRateHz, numel(waveformV)); ...
    ""; ...
    "Data"; ...
    "Channel 0 (PXI1Slot2/0)"];
writelines(header, csvPath);
writematrix(waveformV, csvPath, WriteMode="append");
end
