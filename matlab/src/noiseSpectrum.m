function [pxx, f] = noiseSpectrum(noiseWaveform, fs, N, doPlot)
%NOISESPECTRUM Estimate the one-sided PSD of a real noise waveform.
%   [PXX, F] = NOISESPECTRUM(X, FS, N) estimates the one-sided power
%   spectral density (PSD) of X with Welch's method. FS is the sampling
%   rate in hertz and N is both the Welch segment length and FFT length.
%   Successive periodic-Hann segments have 50 percent overlap.
%
%   [PXX, F] = NOISESPECTRUM(X, FS, N, DOPLOT) also controls plotting.
%   DOPLOT defaults to false. When it is true, the function plots both the
%   PSD and its square root (the amplitude spectral density).
%
%   PXX has units of X-unit^2/Hz, and F has units of Hz. The DC component
%   is removed from the complete waveform before spectral estimation.
%
%   Requirements and interpretation of N:
%     * X must be a finite, real, nonempty vector.
%     * N must be an integer satisfying 2 <= N <= numel(X).
%     * If numel(X) == N, the result contains one windowed periodogram.
%       Longer records contain multiple averaged Welch segments.
%
%   Example:
%       fs = 100e3;
%       x = 2e-3*randn(10*fs/100, 1);
%       [pxx, f] = noiseSpectrum(x, fs, 4096, true);

arguments
    noiseWaveform {mustBeReal, mustBeFinite, mustBeVector, mustBeNonempty}
    fs (1, 1) double {mustBeFinite, mustBePositive}
    N (1, 1) double {mustBeFinite, mustBeInteger, mustBeGreaterThanOrEqual(N, 2)}
    doPlot (1, 1) logical = false
end

noiseWaveform = double(noiseWaveform(:));
if N > numel(noiseWaveform)
    error("noiseSpectrum:InsufficientSamples", ...
        "N (%d) cannot exceed the waveform length (%d).", ...
        N, numel(noiseWaveform));
end

noiseWaveform = noiseWaveform-mean(noiseWaveform);
window = hann(N, "periodic");
overlapLength = floor(N/2);
[pxx, f] = pwelch( ...
    noiseWaveform, window, overlapLength, N, fs, "onesided");

if doPlot
    plotNoiseSpectrum(pxx, f);
end
end

function plotNoiseSpectrum(pxx, f)
figure(Name="Noise spectrum", Color="w");
layout = tiledlayout(2, 1, TileSpacing="compact", Padding="compact");
use = f > 0;

nexttile;
loglog(f(use), max(pxx(use), realmin("double")), LineWidth=1.1);
grid on;
xlabel("Frequency (Hz)");
ylabel("PSD (unit^2/Hz)");
title("One-sided noise power spectral density");
xlim([f(find(use, 1, "first")), f(end)]);

nexttile;
loglog(f(use), sqrt(max(pxx(use), realmin("double"))), LineWidth=1.1);
grid on;
xlabel("Frequency (Hz)");
ylabel("ASD (unit/sqrt(Hz))");
title("One-sided noise amplitude spectral density");
xlim([f(find(use, 1, "first")), f(end)]);

title(layout, "Welch noise spectrum");
end
