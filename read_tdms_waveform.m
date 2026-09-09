function [waveformV, sampleRateHz, timeSeconds, channelName] = ...
        read_tdms_waveform(tdmsw)
%READ_TDMS_WAVEFORM Read the time-domain Channel 0 waveform from a TDMS file.
%
%   waveformV = READ_TDMS_WAVEFORM(tdmsw) returns Channel 0 as a real,
%   finite column vector. The samples are returned unchanged: this function
%   does not remove the mean, detrend, window, filter, or resample them.
%
%   [waveformV, sampleRateHz] = READ_TDMS_WAVEFORM(tdmsw) also returns the
%   sample rate obtained from the TDMS wf_increment property.
%
%   [waveformV, sampleRateHz, timeSeconds, channelName] additionally returns
%   the TDMS time axis and the selected channel name.
%
%   Requirement: MATLAB R2022a or newer with Data Acquisition Toolbox.
%
%   Example using PERIODGRAM (Signal Processing Toolbox):
%       tdmsw = "Instrument Capture 2026-08-28.tdms";
%       [x, Fs] = read_tdms_waveform(tdmsw);
%       x = x - mean(x);
%       N = numel(x);
%       w = hamming(N, "periodic");
%       [psdV2PerHz, frequencyHz] = ...
%           periodogram(x, w, N, Fs, "onesided");
%       asdVPerSqrtHz = sqrt(psdV2PerHz);
%       use = frequencyHz >= 1;
%       loglog(frequencyHz(use), asdVPerSqrtHz(use));
%       grid on;
%       xlabel("Frequency (Hz)");
%       ylabel("Voltage noise density (V/\surdHz)");

arguments
    tdmsw (1, 1) string
end

assert(isfile(tdmsw), "TDMS file was not found: %s", tdmsw);

fileInfo = tdmsinfo(tdmsw);
channelList = fileInfo.ChannelList;
assert(~isempty(channelList), "The TDMS file has no channels: %s", tdmsw);

channelNames = string(channelList.ChannelName);
groupNames = string(channelList.ChannelGroupName);
dataTypes = string(channelList.DataType);

% InstrumentStudio can store both time-domain and FFT channels. Select only
% the double-precision Channel 0 waveform from the waveform-data group.
matches = contains(lower(channelNames), "channel 0") & ...
    contains(lower(groupNames), "waveform data") & ...
    strcmpi(dataTypes, "Double") & ...
    ~contains(lower(channelNames), "fft");
rows = find(matches);
assert(numel(rows) == 1, ...
    "Expected one time-domain Channel 0 in %s, but found %d.", ...
    tdmsw, numel(rows));

row = rows(1);
channelName = channelNames(row);
groupName = groupNames(row);

channelProperties = tdmsreadprop(tdmsw, ...
    ChannelGroupName=groupName, ChannelName=channelName);
sampleIntervalSeconds = getNumericProperty( ...
    channelProperties, "wf_increment");
startTimeSeconds = getNumericProperty( ...
    channelProperties, "wf_start_offset");
assert(isfinite(sampleIntervalSeconds) && sampleIntervalSeconds > 0, ...
    "Invalid wf_increment in TDMS file: %s", tdmsw);
sampleRateHz = 1/sampleIntervalSeconds;

selectedData = tdmsread(tdmsw, ...
    ChannelGroupName=groupName, ChannelNames=channelName);
waveformV = double(selectedData{1}{:, 1});

lastValid = find(~ismissing(waveformV), 1, "last");
assert(~isempty(lastValid), ...
    "Channel 0 contains no waveform samples: %s", tdmsw);
waveformV = waveformV(1:lastValid);
assert(isreal(waveformV) && all(isfinite(waveformV)), ...
    "Channel 0 contains missing, infinite, or complex samples: %s", ...
    tdmsw);
waveformV = waveformV(:);

if nargout >= 3
    timeSeconds = startTimeSeconds + ...
        (0:numel(waveformV)-1).' / sampleRateHz;
else
    timeSeconds = [];
end
end

function value = getNumericProperty(propertyTable, propertyName)
variableNames = string(propertyTable.Properties.VariableNames);
index = find(strcmpi(variableNames, propertyName), 1, "first");
assert(~isempty(index), ...
    "Required TDMS property '%s' was not found.", propertyName);
value = double(propertyTable{1, index});
end
