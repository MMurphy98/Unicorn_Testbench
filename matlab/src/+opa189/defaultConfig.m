function cfg = defaultConfig()
%DEFAULTCONFIG Return the authoritative OPA189 noise-analysis settings.

cfg = struct;
cfg.expectedSampleRateHz = 50e3;
cfg.sampleRateToleranceFraction = 1e-6;
cfg.segmentDurationS = 10;
cfg.overlapFraction = 0.50;
cfg.noiseGain = 1001;
cfg.analysisBandHz = [0.1, 100];
cfg.quietBandHz = [5, 40];
cfg.integrationBandsHz = [0.1, 10; 0.1, 100];
end
