function writeCampaignFigures( ...
        plotData, conditionKeys, cobNumbers, cfg, paths)
%WRITECAMPAIGNFIGURES Export the two DUT comparison figure layouts.

byCobFigure = plotByCob( ...
    plotData, conditionKeys, cobNumbers, cfg);
cleanupCob = onCleanup(@() close(byCobFigure));
exportgraphics(byCobFigure, paths.byCobPng, Resolution=300);
if isfield(paths, "byCobFig") && strlength(paths.byCobFig) > 0
    savefig(byCobFigure, paths.byCobFig);
end

byBiasFigure = plotByBias( ...
    plotData, conditionKeys, cobNumbers, cfg);
cleanupBias = onCleanup(@() close(byBiasFigure));
exportgraphics(byBiasFigure, paths.byBiasPng, Resolution=300);
if isfield(paths, "byBiasFig") && strlength(paths.byBiasFig) > 0
    savefig(byBiasFigure, paths.byBiasFig);
end
end

function figureHandle = plotByCob( ...
        plotData, conditionKeys, cobNumbers, cfg)
figureHandle = figure(Visible="off", Color="w", ...
    Name="DUT input-referred noise by COB");
applyLightTheme(figureHandle);
layout = tiledlayout(numel(cobNumbers), 1, ...
    TileSpacing="compact", Padding="compact");
for cobNumber = cobNumbers
    axisHandle = nexttile(layout);
    hold(axisHandle, "on");
    for biasCurrentMicroA = cfg.biasCurrentsMicroA
        key = sprintf("COB%d_%duA", cobNumber, biasCurrentMicroA);
        conditionIndex = find(conditionKeys == key, 1);
        loglog(axisHandle, plotData.frequencyHz, ...
            plotData.inputAsdVrtHz(:, conditionIndex)*1e9, ...
            DisplayName=sprintf("%d uA", biasCurrentMicroA), ...
            LineWidth=1.1);
    end
    addOpa189Reference(axisHandle);
    configureAxis(axisHandle, sprintf("COB %d", cobNumber), ...
        cfg.plotFrequencyLimitsHz);
end
configureSharedLegend(axisHandle);
xlabel(layout, "Frequency (Hz)");
ylabel(layout, "Input-referred ASD (nV/sqrt(Hz))");
title(layout, "DUT noise: bias-current comparison by COB");
end

function figureHandle = plotByBias( ...
        plotData, conditionKeys, cobNumbers, cfg)
figureHandle = figure(Visible="off", Color="w", ...
    Name="DUT input-referred noise by bias current");
applyLightTheme(figureHandle);
layout = tiledlayout(numel(cfg.biasCurrentsMicroA), 1, ...
    TileSpacing="compact", Padding="compact");
for biasCurrentMicroA = cfg.biasCurrentsMicroA
    axisHandle = nexttile(layout);
    hold(axisHandle, "on");
    for cobNumber = cobNumbers
        key = sprintf("COB%d_%duA", cobNumber, biasCurrentMicroA);
        conditionIndex = find(conditionKeys == key, 1);
        loglog(axisHandle, plotData.frequencyHz, ...
            plotData.inputAsdVrtHz(:, conditionIndex)*1e9, ...
            DisplayName=sprintf("COB %d", cobNumber), ...
            LineWidth=1.1);
    end
    addOpa189Reference(axisHandle);
    configureAxis(axisHandle, sprintf("Ib2 = Ib3 = %d uA", ...
        biasCurrentMicroA), cfg.plotFrequencyLimitsHz);
end
configureSharedLegend(axisHandle);
xlabel(layout, "Frequency (Hz)");
ylabel(layout, "Input-referred ASD (nV/sqrt(Hz))");
title(layout, "DUT noise: COB comparison by bias current");
end

function addOpa189Reference(axisHandle)
yline(axisHandle, 5.2, "--", ...
    DisplayName="OPA189 typ.: 5.2 nV/sqrt(Hz) @ 1 kHz", ...
    Color=[0.85, 0.325, 0.098], ...
    LineWidth=1.4);
end

function configureSharedLegend(axisHandle)
legendHandle = legend(axisHandle, Orientation="horizontal");
legendHandle.Layout.Tile = "north";
set(legendHandle, ...
    Color="w", ...
    TextColor="k", ...
    EdgeColor=[0.35, 0.35, 0.35]);
end

function configureAxis(axisHandle, plotTitle, limitsHz)
set(axisHandle, ...
    XScale="log", ...
    YScale="log", ...
    Color="w", ...
    XColor=[0.15, 0.15, 0.15], ...
    YColor=[0.15, 0.15, 0.15], ...
    GridColor=[0.72, 0.72, 0.72], ...
    MinorGridColor=[0.84, 0.84, 0.84], ...
    GridAlpha=0.45, ...
    MinorGridAlpha=0.30, ...
    Box="on");
grid(axisHandle, "on");
grid(axisHandle, "minor");
xlim(axisHandle, limitsHz);
title(axisHandle, plotTitle);
end

function applyLightTheme(figureHandle)
if ~isempty(which("theme"))
    theme(figureHandle, "light");
end
end
