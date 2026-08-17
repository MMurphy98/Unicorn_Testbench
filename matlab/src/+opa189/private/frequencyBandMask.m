function mask = frequencyBandMask(frequencyHz, limitsHz)
%FREQUENCYBANDMASK Select nominal band edges despite roundoff in FFT bins.

frequencyHz = frequencyHz(:);
limitsHz = reshape(limitsHz, 1, []);
if numel(limitsHz) ~= 2 || limitsHz(1) > limitsHz(2)
    error("opa189:InvalidFrequencyBand", ...
        "Frequency limits must be an increasing two-element vector.");
end

if numel(frequencyHz) > 1
    resolutionHz = median(abs(diff(frequencyHz)));
else
    resolutionHz = 0;
end
frequencyScaleHz = max([1; abs(frequencyHz); abs(limitsHz(:))]);
roundoffFractionOfBin = 1e-8;
toleranceHz = max( ...
    32*eps(frequencyScaleHz), ...
    resolutionHz*roundoffFractionOfBin);

mask = frequencyHz >= limitsHz(1)-toleranceHz & ...
    frequencyHz <= limitsHz(2)+toleranceHz;
end
