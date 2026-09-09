function outputPath = export_spectra_npz_to_mat(inputDir, outputPath)
%EXPORT_SPECTRA_NPZ_TO_MAT Consolidate numbered spectrum NPZ files into MAT.
%   OUTPUTPATH = EXPORT_SPECTRA_NPZ_TO_MAT(INPUTDIR, OUTPUTPATH) validates
%   all numbered *_spectrum.npz files in INPUTDIR, stores each run as one
%   matrix column, and adds the ensemble-average PSD and ASD.
%
%   Matrix convention:
%     rows    = frequency bins
%     columns = runs ordered by run number
%
%   The ensemble ASD is sqrt(mean(PSD, 2)), matching the aggregate plot
%   calculation used by plot_dut_revb_pmu_noise.py.

arguments
    inputDir (1, 1) string
    outputPath (1, 1) string = ""
end

inputDir = string(java.io.File(char(inputDir)).getCanonicalPath());
assert(isfolder(inputDir), "Input directory does not exist: %s", inputDir);

files = dir(fullfile(inputDir, "*_spectrum.npz"));
assert(~isempty(files), "No *_spectrum.npz files found in %s", inputDir);

runNumbersFromNames = zeros(numel(files), 1, "int64");
for fileIndex = 1:numel(files)
    token = regexp(files(fileIndex).name, "_(\d+)_spectrum\.npz$", ...
        "tokens", "once");
    assert(~isempty(token), "Cannot parse run number from %s", ...
        files(fileIndex).name);
    runNumbersFromNames(fileIndex) = int64(str2double(token{1}));
end
[runNumbersFromNames, order] = sort(runNumbersFromNames);
files = files(order);
assert(numel(unique(runNumbersFromNames)) == numel(files), ...
    "Duplicate run numbers were found.");

if outputPath == ""
    [~, taskFolderName] = fileparts(inputDir);
    outputPath = fullfile(inputDir, taskFolderName + ...
        "_100run_spectra_with_mean.mat");
end
outputPath = string(java.io.File(char(outputPath)).getCanonicalPath());
assert(~isfile(outputPath), "Refusing to overwrite existing file: %s", ...
    outputPath);

temporaryRoot = string(tempname);
mkdir(temporaryRoot);
temporaryCleanup = onCleanup(@() removeTemporaryDirectory(temporaryRoot));

runCount = numel(files);
sourceSpectrumFiles = cell(runCount, 1);
sourceTdmsPaths = cell(runCount, 1);
runNumbers = zeros(runCount, 1, "int64");
welchSegmentCountByRun = zeros(runCount, 1, "int64");

frequencyHz = [];
inputPsdV2PerHzByRun = [];
reference = struct();

for runIndex = 1:runCount
    archivePath = fullfile(files(runIndex).folder, files(runIndex).name);
    extractionDir = fullfile(temporaryRoot, sprintf("run_%04d", runIndex));
    mkdir(extractionDir);
    unzip(archivePath, extractionDir);

    currentFrequencyHz = double(readNpySimple( ...
        fullfile(extractionDir, "frequency_hz.npy")));
    currentPsd = double(readNpySimple( ...
        fullfile(extractionDir, "input_psd_v2_per_hz.npy")));
    currentFrequencyHz = currentFrequencyHz(:);
    currentPsd = currentPsd(:);

    assert(numel(currentFrequencyHz) == numel(currentPsd), ...
        "Frequency/PSD length mismatch in %s", files(runIndex).name);
    assert(all(isfinite(currentFrequencyHz)) && ...
        all(isfinite(currentPsd)) && all(currentPsd >= 0), ...
        "Non-finite frequency/PSD or negative PSD in %s", ...
        files(runIndex).name);
    assert(all(diff(currentFrequencyHz) > 0), ...
        "Frequency grid is not strictly increasing in %s", ...
        files(runIndex).name);

    currentRunNumber = int64(readNpySimple( ...
        fullfile(extractionDir, "run_number.npy")));
    assert(currentRunNumber == runNumbersFromNames(runIndex), ...
        "Run-number metadata mismatch in %s", files(runIndex).name);

    current = readRunMetadata(extractionDir);
    if runIndex == 1
        frequencyHz = currentFrequencyHz;
        inputPsdV2PerHzByRun = zeros(numel(frequencyHz), runCount);
        reference = current;
    else
        assert(isequal(currentFrequencyHz, frequencyHz), ...
            "Frequency grid mismatch in %s", files(runIndex).name);
        assertMetadataMatches(reference, current, files(runIndex).name);
    end

    inputPsdV2PerHzByRun(:, runIndex) = currentPsd;
    runNumbers(runIndex) = currentRunNumber;
    welchSegmentCountByRun(runIndex) = current.welchSegmentCount;
    sourceSpectrumFiles{runIndex} = files(runIndex).name;
    sourceTdmsPaths{runIndex} = char(readNpySimple( ...
        fullfile(extractionDir, "source_tdms.npy")));

    rmdir(extractionDir, "s");
    fprintf("Loaded %d/%d: run %d\n", runIndex, runCount, currentRunNumber);
end

% Average power first. This is the same definition used by the project's
% aggregate plotting script and avoids bias from averaging amplitudes.
meanInputPsdV2PerHz = mean(inputPsdV2PerHzByRun, 2);
inputAsdVPerSqrtHzByRun = sqrt(inputPsdV2PerHzByRun);
meanInputAsdVPerSqrtHz = sqrt(meanInputPsdV2PerHz);

metadata = struct();
metadata.schemaVersion = int64(1);
metadata.description = [ ...
    "Consolidated input-referred one-sided Welch spectra. " ...
    "Rows are frequency bins; columns are runs ordered by runNumbers."];
metadata.averageDefinition = [ ...
    "meanInputPsdV2PerHz = mean(inputPsdV2PerHzByRun, 2); " ...
    "meanInputAsdVPerSqrtHz = sqrt(meanInputPsdV2PerHz)."];
metadata.sourceSpectrumFormatVersion = reference.formatVersion;
metadata.taskId = reference.taskId;
metadata.channelName = reference.channelName;
metadata.runCount = int64(runCount);
metadata.frequencyBinCount = int64(numel(frequencyHz));
metadata.sampleRateHz = reference.sampleRateHz;
metadata.closedLoopGainVPerV = reference.closedLoopGainVPerV;
metadata.estimatedClosedLoopBandwidthHz = ...
    reference.estimatedClosedLoopBandwidthHz;
metadata.sourceSampleCount = reference.sourceSampleCount;
metadata.frequencyResolutionHz = reference.frequencyResolutionHz;
metadata.welchWindow = reference.welchWindow;
metadata.welchNperseg = reference.welchNperseg;
metadata.welchNoverlap = reference.welchNoverlap;
metadata.welchDetrend = reference.welchDetrend;
metadata.welchAverage = reference.welchAverage;
metadata.totalWelchSegmentCount = sum(welchSegmentCountByRun);
metadata.units = struct( ...
    "frequencyHz", "Hz", ...
    "inputPsdV2PerHzByRun", "V^2/Hz", ...
    "meanInputPsdV2PerHz", "V^2/Hz", ...
    "inputAsdVPerSqrtHzByRun", "V/sqrt(Hz)", ...
    "meanInputAsdVPerSqrtHz", "V/sqrt(Hz)");

save(outputPath, "frequencyHz", "runNumbers", ...
    "inputPsdV2PerHzByRun", "inputAsdVPerSqrtHzByRun", ...
    "meanInputPsdV2PerHz", "meanInputAsdVPerSqrtHz", ...
    "welchSegmentCountByRun", "sourceSpectrumFiles", ...
    "sourceTdmsPaths", "metadata", "-v7");

outputInfo = dir(outputPath);
fprintf("Saved %s (%.1f MiB)\n", outputPath, outputInfo.bytes/2^20);
clear temporaryCleanup
end


function metadata = readRunMetadata(extractionDir)
metadata = struct();
metadata.formatVersion = int64(readNpySimple( ...
    fullfile(extractionDir, "format_version.npy")));
metadata.taskId = string(readNpySimple( ...
    fullfile(extractionDir, "task_id.npy")));
metadata.channelName = string(readNpySimple( ...
    fullfile(extractionDir, "channel_name.npy")));
metadata.sampleRateHz = double(readNpySimple( ...
    fullfile(extractionDir, "sample_rate_hz.npy")));
metadata.closedLoopGainVPerV = double(readNpySimple( ...
    fullfile(extractionDir, "closed_loop_gain_v_per_v.npy")));
metadata.estimatedClosedLoopBandwidthHz = double(readNpySimple( ...
    fullfile(extractionDir, "estimated_closed_loop_bandwidth_hz.npy")));
metadata.sourceSampleCount = int64(readNpySimple( ...
    fullfile(extractionDir, "source_sample_count.npy")));
metadata.welchWindow = string(readNpySimple( ...
    fullfile(extractionDir, "welch_window.npy")));
metadata.welchNperseg = int64(readNpySimple( ...
    fullfile(extractionDir, "welch_nperseg.npy")));
metadata.welchNoverlap = int64(readNpySimple( ...
    fullfile(extractionDir, "welch_noverlap.npy")));
metadata.welchDetrend = string(readNpySimple( ...
    fullfile(extractionDir, "welch_detrend.npy")));
metadata.welchAverage = string(readNpySimple( ...
    fullfile(extractionDir, "welch_average.npy")));
metadata.welchSegmentCount = int64(readNpySimple( ...
    fullfile(extractionDir, "welch_segment_count.npy")));
metadata.frequencyResolutionHz = double(readNpySimple( ...
    fullfile(extractionDir, "frequency_resolution_hz.npy")));
end


function assertMetadataMatches(reference, current, fileName)
constantFields = [ ...
    "formatVersion", "taskId", "channelName", "sampleRateHz", ...
    "closedLoopGainVPerV", "estimatedClosedLoopBandwidthHz", ...
    "sourceSampleCount", "welchWindow", "welchNperseg", ...
    "welchNoverlap", "welchDetrend", "welchAverage", ...
    "frequencyResolutionHz"];
for fieldIndex = 1:numel(constantFields)
    fieldName = constantFields(fieldIndex);
    assert(isequal(reference.(fieldName), current.(fieldName)), ...
        "Metadata field %s differs in %s", fieldName, fileName);
end
end


function value = readNpySimple(filePath)
% Minimal NumPy .npy v1/v2 reader for scalar and 1-D little-endian arrays.
fid = fopen(filePath, "r", "ieee-le");
assert(fid >= 0, "Cannot open %s", filePath);
fileCleanup = onCleanup(@() fclose(fid));

magic = fread(fid, 6, "*uint8").';
assert(isequal(magic, uint8([147, double('NUMPY')])), ...
    "Invalid NPY magic in %s", filePath);
version = fread(fid, 2, "*uint8");
assert(numel(version) == 2 && any(version(1) == [1, 2]), ...
    "Unsupported NPY version in %s", filePath);
if version(1) == 1
    headerLength = fread(fid, 1, "uint16=>double");
else
    headerLength = fread(fid, 1, "uint32=>double");
end
header = char(fread(fid, headerLength, "*uint8").');

descriptorToken = regexp(header, ...
    "'descr':\s*'([^']+)'", "tokens", "once");
shapeToken = regexp(header, ...
    "'shape':\s*\(([^)]*)\)", "tokens", "once");
assert(~isempty(descriptorToken) && ~isempty(shapeToken), ...
    "Cannot parse NPY header in %s", filePath);
assert(contains(header, "'fortran_order': False"), ...
    "Fortran-order NPY arrays are not supported: %s", filePath);

descriptor = descriptorToken{1};
dimensionTokens = regexp(shapeToken{1}, "\d+", "match");
if isempty(dimensionTokens)
    elementCount = 1;
else
    shape = cellfun(@str2double, dimensionTokens);
    assert(numel(shape) <= 1, ...
        "Only scalar and 1-D NPY arrays are supported: %s", filePath);
    elementCount = prod(shape);
end

switch descriptor
    case "<f8"
        value = fread(fid, elementCount, "float64=>double");
    case "<i8"
        value = fread(fid, elementCount, "int64=>int64");
    otherwise
        unicodeToken = regexp(descriptor, "^<U(\d+)$", ...
            "tokens", "once");
        assert(~isempty(unicodeToken) && elementCount == 1, ...
            "Unsupported NPY dtype %s in %s", descriptor, filePath);
        characterCount = str2double(unicodeToken{1});
        codePoints = fread(fid, characterCount, "uint32=>uint32");
        codePoints = codePoints(codePoints ~= 0);
        value = char(codePoints.');
end

assert(~isnumeric(value) || numel(value) == elementCount, ...
    "Unexpected end of NPY data in %s", filePath);
clear fileCleanup
end


function removeTemporaryDirectory(directoryPath)
if isfolder(directoryPath)
    rmdir(directoryPath, "s");
end
end
