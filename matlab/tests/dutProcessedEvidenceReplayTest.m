classdef dutProcessedEvidenceReplayTest < matlab.unittest.TestCase
    %DUTPROCESSEDEVIDENCEREPLAYTEST Tests compact evidence replay paths.

    methods (TestClassSetup)
        function addSourceToPath(testCase)
            testDir = fileparts(mfilename("fullpath"));
            matlabDir = fileparts(testDir);
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "src"), IncludingSubfolders=true));
        end
    end

    methods (Test)
        function testSupplyComparisonReplaysFromCompactMat(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            plotF = [1; 10; 100; 1e3; 1e4];
            plotP = ([40, 25; 20, 14; 9, 7; 5.8, 5.4; 5.5, 5.3]*1e-9).^2;
            plotA = sqrt(plotP)*1e9;
            comparisonSummary = array2table( ...
                [40, 25; 5.5, 5.3], ...
                VariableNames=["ASD_1Hz_nVrtHz", "Median_1k_10k"]);
            conditionLabels = [ ...
                "+/-3 V, 10 captures"; ...
                "+/-6 V, 10 captures"];
            referenceNvRtHz = 5.2;
            save(fullfile(workDir, "supply_voltage_plot_data.mat"), ...
                "plotF", "plotP", "plotA", "comparisonSummary", ...
                "conditionLabels", "referenceNvRtHz");

            paths = dut.replaySupplyComparison(workDir);
            pngInfo = imfinfo(paths.comparisonPng);

            testCase.verifyTrue(isfile(paths.comparisonPng));
            testCase.verifyEqual([pngInfo.Width, pngInfo.Height], ...
                [1800, 1100]);
        end

        function testRepeatedConditionReplaysFromCompactMat(testCase)
            workDir = string(tempname);
            mkdir(workDir);
            testCase.addTeardown(@() rmdir(workDir, "s"));

            plotFrequencyHz = [1; 10; 100; 1e3; 1e4];
            plotInputAsdVrtHz = [40; 20; 9; 5.8; 5.4]*1e-9;
            plotInputPsdV2PerHz = plotInputAsdVrtHz.^2;
            processedRunSummary = table((1:2)', ...
                VariableNames="RunNumber");
            conditionSummary = table(2, VariableNames="RunCount");
            runCount = 2;
            cfg = struct( ...
                plotFrequencyLimitsHz=[1, 1e4], ...
                referenceNvRtHz=5.1, ...
                testLabel="Synthetic repeated condition", ...
                figureSubtitle="Two-capture PSD average");
            save(fullfile(workDir, "with50ohm_plot_data.mat"), ...
                "plotFrequencyHz", "plotInputPsdV2PerHz", ...
                "plotInputAsdVrtHz", "processedRunSummary", ...
                "conditionSummary", "runCount", "cfg");
            initialImagePath = fullfile( ...
                workDir, "initial_measurement_reference.png");
            imwrite(uint8(240*ones(40, 60, 3)), initialImagePath);

            paths = dut.replayRepeatedCondition(workDir);
            spectrumInfo = imfinfo(paths.sameFormatPng);
            comparisonInfo = imfinfo(paths.comparisonPng);

            testCase.verifyEqual( ...
                [spectrumInfo.Width, spectrumInfo.Height], [1515, 1293]);
            testCase.verifyEqual( ...
                [comparisonInfo.Width, comparisonInfo.Height], [3000, 1320]);
        end
    end
end
