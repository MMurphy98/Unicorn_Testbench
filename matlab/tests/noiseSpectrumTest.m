classdef noiseSpectrumTest < matlab.unittest.TestCase
    %NOISESPECTRUMTEST Tests the generic noise-spectrum estimator.

    methods (TestClassSetup)
        function addSourceToPath(testCase)
            testDir = fileparts(mfilename("fullpath"));
            matlabDir = fileparts(testDir);
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(matlabDir, "src")));
        end
    end

    methods (Test)
        function testOutputSizeAndFrequencyAxis(testCase)
            fs = 1000;
            N = 256;
            x = zeros(4*N, 1);

            [pxx, f] = noiseSpectrum(x, fs, N);

            testCase.verifySize(pxx, [N/2+1, 1]);
            testCase.verifySize(f, [N/2+1, 1]);
            testCase.verifyEqual(f(1), 0);
            testCase.verifyEqual(f(end), fs/2);
            testCase.verifyEqual(diff(f), ...
                repmat(fs/N, N/2, 1), AbsTol=10*eps(fs));
            testCase.verifyEqual(pxx, zeros(N/2+1, 1));
        end

        function testPsdIntegralRecoversWhiteNoiseVariance(testCase)
            originalState = rng;
            cleanup = onCleanup(@() rng(originalState));
            rng(7, "twister");
            fs = 20e3;
            N = 2048;
            sigma = 3e-3;
            x = sigma*randn(100*N, 1);

            [pxx, f] = noiseSpectrum(x, fs, N);
            estimatedVariance = trapz(f, pxx);

            testCase.verifyEqual(estimatedVariance, sigma^2, RelTol=0.04);
        end

        function testRowInputProducesColumnOutputs(testCase)
            [pxx, f] = noiseSpectrum(1:16, 8, 8);

            testCase.verifyTrue(iscolumn(pxx));
            testCase.verifyTrue(iscolumn(f));
        end

        function testTooFewSamplesErrors(testCase)
            action = @() noiseSpectrum(ones(10, 1), 100, 16);

            testCase.verifyError(action, ...
                "noiseSpectrum:InsufficientSamples");
        end

        function testPlotOptionCreatesFigure(testCase)
            oldVisibility = get(groot, "DefaultFigureVisible");
            testCase.addTeardown(@() set(groot, ...
                "DefaultFigureVisible", oldVisibility));
            set(groot, "DefaultFigureVisible", "off");
            figuresBefore = findall(groot, Type="figure");

            noiseSpectrum(randn(1024, 1), 1000, 256, true);

            figuresAfter = findall(groot, Type="figure");
            newFigures = setdiff(figuresAfter, figuresBefore);
            testCase.addTeardown(@() delete(newFigures));
            testCase.verifyNumElements(newFigures, 1);
            axesHandles = findall(newFigures, Type="axes");
            testCase.verifyNumElements(axesHandles, 2);
            for axisHandle = axesHandles.'
                testCase.verifyEqual(axisHandle.XScale, 'log');
                testCase.verifyEqual(axisHandle.YScale, 'log');
                testCase.verifyGreaterThan(axisHandle.XLim(1), 0);
            end
        end
    end
end
