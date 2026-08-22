function paths = replayProcessedCampaign(processedDir)
%REPLAYPROCESSEDCAMPAIGN Regenerate figures without raw waveform CSVs.

arguments
    processedDir (1, 1) string
end

matPath = fullfile(processedDir, "dut_noise_plot_data.mat");
if ~isfile(matPath)
    error("dut:MissingProcessedData", ...
        "Compact DUT plot data does not exist: %s", matPath);
end
saved = load(matPath);
requiredFields = [ ...
    "plotFrequencyHz", "plotInputPsdV2PerHz", ...
    "plotInputAsdVrtHz", "conditionKeys", ...
    "cobNumbers", "cfg"];
if ~all(isfield(saved, requiredFields))
    error("dut:InvalidProcessedData", ...
        "Compact DUT plot data is missing required fields: %s", ...
        matPath);
end

plotData = struct;
plotData.frequencyHz = saved.plotFrequencyHz;
plotData.inputPsdV2PerHz = saved.plotInputPsdV2PerHz;
plotData.inputAsdVrtHz = saved.plotInputAsdVrtHz;
paths = struct;
paths.byCobPng = fullfile(processedDir, "dut_noise_by_cob.png");
paths.byBiasPng = fullfile(processedDir, "dut_noise_by_bias.png");
paths.byCobFig = "";
paths.byBiasFig = "";
writeCampaignFigures( ...
    plotData, saved.conditionKeys, saved.cobNumbers, saved.cfg, paths);
end
