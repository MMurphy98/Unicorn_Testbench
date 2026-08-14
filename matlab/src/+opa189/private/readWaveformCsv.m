function record = readWaveformCsv(csvPath)
%READWAVEFORMCSV Read a complete InstrumentStudio waveform export.

[metadataLine, dataHeaderLine] = locateSections(csvPath);
metadataFields = split(string(metadataLine), ",");
if numel(metadataFields) < 4
    error("opa189:IncompleteMetadata", ...
        "The physical-channel metadata is incomplete.");
end

sampleIntervalS = parseScalar(metadataFields(3), "sample interval");
sampleCount = parseCount(metadataFields(4));
if ~(sampleIntervalS > 0)
    error("opa189:InvalidSampleInterval", ...
        "The waveform sample interval must be positive.");
end

numericData = readmatrix(csvPath, ...
    NumHeaderLines=dataHeaderLine, OutputType="double");
if isempty(numericData) || size(numericData, 2) < 1
    error("opa189:MissingWaveformData", ...
        "The waveform data column was not found.");
end
voltageV = numericData(:, 1);
if any(~isfinite(voltageV))
    error("opa189:NonfiniteWaveformSample", ...
        "The waveform contains missing or nonfinite samples.");
end
if numel(voltageV) ~= sampleCount
    error("opa189:WaveformSampleCountMismatch", ...
        "Metadata declares %d samples, but %d were imported.", ...
        sampleCount, numel(voltageV));
end

record = struct;
record.path = char(csvPath);
record.physicalChannel = char(strtrim(metadataFields(1)));
record.sampleIntervalS = sampleIntervalS;
record.sampleCount = sampleCount;
record.sampleRateHz = 1/sampleIntervalS;
record.durationS = sampleCount*sampleIntervalS;
record.voltageV = voltageV;
end

function [metadataLine, dataHeaderLine] = locateSections(csvPath)
fileId = fopen(csvPath, "r");
if fileId < 0
    error("opa189:CannotOpenCaptureFile", ...
        "Cannot open InstrumentStudio waveform: %s", csvPath);
end
cleanup = onCleanup(@() fclose(fileId)); %#ok<NASGU>

metadataLine = "";
dataHeaderLine = NaN;
lineNumber = 0;
while true
    line = fgetl(fileId);
    if ~ischar(line)
        break;
    end
    lineNumber = lineNumber + 1;
    trimmed = strtrim(line);
    if startsWith(trimmed, "Physical channel,", IgnoreCase=true)
        metadataLine = string(fgetl(fileId));
        lineNumber = lineNumber + 1;
    elseif strcmpi(trimmed, "Data")
        channelHeader = fgetl(fileId);
        lineNumber = lineNumber + 1;
        if ~ischar(channelHeader) || ...
                ~startsWith(strtrim(channelHeader), "Channel", ...
                IgnoreCase=true)
            error("opa189:MissingDataHeader", ...
                "The physical-channel data header was not found.");
        end
        dataHeaderLine = lineNumber;
        break;
    end
end
if strlength(metadataLine) == 0
    error("opa189:IncompleteMetadata", ...
        "The physical-channel metadata block was not found.");
end
if isnan(dataHeaderLine)
    error("opa189:MissingDataHeader", ...
        "The waveform data section was not found.");
end
end

function value = parseScalar(textValue, fieldName)
value = str2double(strtrim(textValue));
if ~isfinite(value)
    error("opa189:InvalidMetadataValue", ...
        "The %s metadata value is not finite.", fieldName);
end
end

function value = parseCount(textValue)
value = parseScalar(textValue, "sample count");
if value < 1 || value ~= floor(value)
    error("opa189:InvalidMetadataCount", ...
        "The waveform sample count must be a positive integer.");
end
end
