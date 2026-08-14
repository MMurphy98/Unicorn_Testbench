function result = analyzeWaveform(csvPath, cfg)
%ANALYZEWAVEFORM Compute input-referred Welch PSD from a raw CH0 CSV.

arguments
    csvPath (1, 1) string {mustBeFile}
    cfg (1, 1) struct = opa189.defaultConfig()
end

record = readWaveformCsv(csvPath);
validateRecord(record, cfg);

segmentLength = round(cfg.segmentDurationS*record.sampleRateHz);
overlapLength = floor(cfg.overlapFraction*segmentLength);
window = hann(segmentLength, "periodic");
voltageDetrendedV = detrend(record.voltageV, 1);
[outputPsdV2PerHz, frequencyHz] = pwelch( ...
    voltageDetrendedV, window, overlapLength, segmentLength, ...
    record.sampleRateHz, "onesided");

analysisMask = frequencyHz >= cfg.analysisBandHz(1) & ...
    frequencyHz <= cfg.analysisBandHz(2);
if nnz(analysisMask) < 2
    error("opa189:MissingAnalysisBand", ...
        "The Welch result does not contain the configured analysis band.");
end
frequencyHz = frequencyHz(analysisMask);
outputPsdV2PerHz = outputPsdV2PerHz(analysisMask);
inputPsdV2PerHz = outputPsdV2PerHz/(cfg.noiseGain^2);
inputAsdVrtHz = sqrt(max(inputPsdV2PerHz, 0));
quietMask = frequencyHz >= cfg.quietBandHz(1) & ...
    frequencyHz <= cfg.quietBandHz(2);
[~, mainsIndex] = min(abs(frequencyHz-50));
segmentStep = max(1, segmentLength-overlapLength);
segmentCount = 1 + floor( ...
    (record.sampleCount-segmentLength)/segmentStep);

result = struct;
result.sourcePath = record.path;
result.physicalChannel = record.physicalChannel;
result.sampleIntervalS = record.sampleIntervalS;
result.sampleRateHz = record.sampleRateHz;
result.recordSampleCount = record.sampleCount;
result.recordDurationS = record.durationS;
result.noiseGain = cfg.noiseGain;
result.welchSegmentDurationS = cfg.segmentDurationS;
result.welchSegmentLength = segmentLength;
result.welchOverlapFraction = cfg.overlapFraction;
result.welchOverlapLength = overlapLength;
result.welchSegmentCount = segmentCount;
result.frequencyResolutionHz = record.sampleRateHz/segmentLength;
result.frequencyHz = frequencyHz;
result.outputPsdV2PerHz = outputPsdV2PerHz;
result.inputPsdV2PerHz = inputPsdV2PerHz;
result.outputAsdVrtHz = sqrt(max(outputPsdV2PerHz, 0));
result.inputAsdVrtHz = inputAsdVrtHz;
result.quietBandMedianInputAsdVrtHz = median(inputAsdVrtHz(quietMask));
result.mains50HzInputAsdVrtHz = inputAsdVrtHz(mainsIndex);
result.integratedNoise0p1To10Vrms = integrateBand( ...
    frequencyHz, inputPsdV2PerHz, cfg.integrationBandsHz(1, :));
result.integratedNoise0p1To100Vrms = integrateBand( ...
    frequencyHz, inputPsdV2PerHz, cfg.integrationBandsHz(2, :));
result.analysisMethod = ...
    "Welch PSD from complete raw waveform; linear detrend; periodic Hann.";
end

function validateRecord(record, cfg)
relativeRateError = abs(record.sampleRateHz- ...
    cfg.expectedSampleRateHz)/cfg.expectedSampleRateHz;
if relativeRateError > cfg.sampleRateToleranceFraction
    error("opa189:UnexpectedSampleRate", ...
        "Expected %.9g S/s, but the waveform uses %.9g S/s.", ...
        cfg.expectedSampleRateHz, record.sampleRateHz);
end
if record.durationS < cfg.segmentDurationS
    error("opa189:RecordTooShort", ...
        "The raw record is shorter than one Welch segment.");
end
end

function noiseVrms = integrateBand(frequencyHz, psdV2PerHz, limitsHz)
use = frequencyHz >= limitsHz(1) & frequencyHz <= limitsHz(2);
if nnz(use) < 2
    error("opa189:MissingIntegrationBand", ...
        "The Welch result does not contain the requested integration band.");
end
noiseVrms = sqrt(max(trapz(frequencyHz(use), psdV2PerHz(use)), 0));
end
