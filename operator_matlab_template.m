%% operator_matlab_template_v2_1_0.m
% Generic MATLAB analysis template v3.0.0 for engineering/operator workflows.
%
% Good for:
%   - thermal characterization
%   - sensor data analysis
%   - fleet reliability metrics
%   - repeatability studies
%   - quick report artifact generation
%
% Pattern:
%   CONFIG -> LOAD -> VALIDATE -> PROCESS -> PLOT -> EXPORT
%
% Operator rules:
%   - Keep raw data immutable.
%   - Write derived tables/figures to output folders.
%   - Put reusable behavior in local functions at the bottom.
%   - Prefer explicit config structs over magic constants.
%   - Treat input tables as untrusted until columns/types are validated.
%
% How to run:
%   Open this file in MATLAB and press Run, or call:
%       run("operator_matlab_template.m")

clear; clc;

%% S0. CONFIG

cfg = struct();
cfg.version = "3.0.0";
cfg.author = "V Halcyon";
cfg.projectName = "operator_analysis";
cfg.runId = string(datetime("now", "TimeZone", "UTC", "Format", "yyyyMMdd_HHmmss'_UTC'"));

% Paths: edit these per project.
cfg.rootDir = string(pwd);
cfg.inputFile = fullfile(cfg.rootDir, "data", "raw", "example.csv");
cfg.outputDir = fullfile(cfg.rootDir, "output");
cfg.figureDir = fullfile(cfg.outputDir, "figures");
cfg.tableDir = fullfile(cfg.outputDir, "tables");
cfg.logDir = fullfile(cfg.outputDir, "logs");

% Analysis settings.
cfg.timeColumn = "time_s";
cfg.valueColumns = ["raw_signal", "response"];    % Can be one or many.
cfg.sampleRateHz = 10;
cfg.rollingWindowSamples = 5;

% Plot/export settings.
cfg.theme = "halcyon-dark";                         % "halcyon-dark" or "light"
cfg.saveFigures = true;
cfg.closeFiguresAfterSave = true;
cfg.figureDpi = 200;


% Halcyon palette tokens: soot / amber / signal-blue / moss.
cfg.palette.soot = "#07090D";
cfg.palette.panel = "#282829";
cfg.palette.text = "#F2E8D5";
cfg.palette.brass = "#B88746";
cfg.palette.amber = "#FFBF00";
cfg.palette.rust = "#B7410E";
cfg.palette.copper = "#C97C5D";
cfg.palette.moss = "#8FA37A";
cfg.palette.signalBlue = "#76B7B2";
cfg.palette.violet = "#A77BD4";

% Safety / threshold examples.
cfg.maxSafeValue = Inf;                              % Set per project, e.g. 60 for deg C.
cfg.warnOnThreshold = false;

ensureDir(cfg.outputDir);
ensureDir(cfg.figureDir);
ensureDir(cfg.tableDir);
ensureDir(cfg.logDir);

logMsg("INFO", "Starting analysis run: " + cfg.runId);
writeConfig(cfg);

%% S1. LOAD DATA

if isfile(cfg.inputFile)
    raw = readtable(cfg.inputFile);
    logMsg("OK", "Loaded input file: " + string(cfg.inputFile));
else
    logMsg("WARN", "Input file not found. Creating placeholder dataset.");
    raw = makePlaceholderData(cfg.sampleRateHz);
end

%% S2. VALIDATE DATA

requiredColumns = [cfg.timeColumn, cfg.valueColumns];
validateColumns(raw, requiredColumns);
validateNumericColumns(raw, requiredColumns);

% Keep raw immutable. Use work for derived columns.
work = raw;
t = work.(cfg.timeColumn);

assert(isvector(t), "Time column must be a vector.");
assert(all(isfinite(t)), "Time column must contain finite numeric values.");
assert(issorted(t), "Time column should be sorted ascending for derivatives/plots.");

%% S3. PROCESS / ANALYZE

metrics = struct();
metrics.numSamples = height(raw);
metrics.duration_s = max(t) - min(t);
metrics.nominalSampleRateHz = cfg.sampleRateHz;

for i = 1:numel(cfg.valueColumns)
    col = cfg.valueColumns(i);
    y = work.(col);

    metrics.(matlab.lang.makeValidName(col + "_min")) = min(y, [], "omitnan");
    metrics.(matlab.lang.makeValidName(col + "_max")) = max(y, [], "omitnan");
    metrics.(matlab.lang.makeValidName(col + "_mean")) = mean(y, "omitnan");
    metrics.(matlab.lang.makeValidName(col + "_std")) = std(y, "omitnan");
    metrics.(matlab.lang.makeValidName(col + "_tau_s")) = estimateTimeConstant(t, y);

    smoothName = matlab.lang.makeValidName(col + "_rolling_mean_" + string(cfg.rollingWindowSamples));
    derivName = matlab.lang.makeValidName("d_" + col + "_d_" + cfg.timeColumn);
    work.(smoothName) = movmean(y, cfg.rollingWindowSamples, "omitnan");
    work.(derivName) = finiteDifference(t, y);

    if cfg.warnOnThreshold && any(y > cfg.maxSafeValue, "all")
        logMsg("WARN", col + " exceeded threshold: " + string(cfg.maxSafeValue));
    end
end

metricsTable = struct2table(metrics, "AsArray", true);
metricsPath = fullfile(cfg.tableDir, "metrics_" + cfg.runId + ".csv");
writetable(metricsTable, metricsPath);
logMsg("OK", "Wrote metrics: " + string(metricsPath));

processedPath = fullfile(cfg.tableDir, "processed_" + cfg.runId + ".csv");
writetable(work, processedPath);
logMsg("OK", "Wrote processed table: " + string(processedPath));

%% S4. PLOT

fig = figure("Name", "Primary Signals");
ax = axes(fig);
hold(ax, "on");
applyTheme(fig, ax, cfg.theme);

for i = 1:numel(cfg.valueColumns)
    col = cfg.valueColumns(i);
    plot(ax, t, work.(col), "LineWidth", 1.5, "DisplayName", col);
end

grid(ax, "on");
xlabel(ax, escapeUnderscores(cfg.timeColumn));
ylabel(ax, "Value");
title(ax, cfg.projectName + " — primary signals");
subtitle(ax, "Run " + cfg.runId);
legend(ax, "Location", "best");
applyTheme(fig, ax, cfg.theme); % Apply again so legend inherits styling.

if cfg.saveFigures
    saveFigure(fig, cfg.figureDir, "primary_signals_" + cfg.runId, cfg.figureDpi);
end

%% S5. EXPORT SUMMARY

summaryPath = fullfile(cfg.logDir, "summary_" + cfg.runId + ".txt");
writeSummary(summaryPath, cfg, metrics, processedPath, metricsPath);
logMsg("OK", "Wrote summary: " + string(summaryPath));

if cfg.closeFiguresAfterSave
    close all;
end

logMsg("OK", "Analysis complete.");

%% S6. SYNTAX CRIB / USEFUL CONSTRUCTION SNIPPETS
%
% Table basics:
%   head(raw)
%   raw(1:10, :)                    % first 10 rows
%   raw.time_s                      % one column using dot syntax
%   raw.(cfg.timeColumn)            % dynamic column name from string
%   raw(raw.temp_c > 60, :)         % rows matching a condition
%
% Loops:
%   for i = 1:numel(cfg.valueColumns)
%       col = cfg.valueColumns(i);
%       disp(raw.(col));
%   end
%
% Struct fields:
%   cfg.projectName
%   fields = fieldnames(cfg);
%   cfg.(fields{1})                 % dynamic struct field access
%
% Assertions:
%   assert(isfile(cfg.inputFile), "Input file missing.");
%
% Try/catch:
%   try
%       result = riskyFunction();
%   catch ME
%       warning("Failed: %s", ME.message);
%   end

%% LOCAL FUNCTIONS

function logMsg(level, msg)
    % logMsg Print a timestamped log message.
    ts = string(datetime("now", "Format", "HH:mm:ss"));
    fprintf("%s | %-5s | %s\n", ts, upper(string(level)), string(msg));
end

function ensureDir(pathStr)
    % ensureDir Create a directory if it does not exist.
    if ~isfolder(pathStr)
        mkdir(pathStr);
    end
end

function validateColumns(tbl, requiredColumns)
    % validateColumns Assert that a table contains all required columns.
    existing = string(tbl.Properties.VariableNames);
    missing = setdiff(string(requiredColumns), existing);
    assert(isempty(missing), "Missing required columns: " + strjoin(missing, ", "));
end

function validateNumericColumns(tbl, requiredColumns)
    % validateNumericColumns Assert selected columns are numeric.
    for i = 1:numel(requiredColumns)
        col = requiredColumns(i);
        assert(isnumeric(tbl.(col)), "Column must be numeric: " + col);
    end
end

function raw = makePlaceholderData(sampleRateHz)
    % makePlaceholderData Create a synthetic dataset so the template can run.
    if nargin < 1 || sampleRateHz <= 0
        sampleRateHz = 10;
    end
    t = (0:1/sampleRateHz:20).';
    command = double(t >= 2.0);
    response = 1 - exp(-max(t - 2.0, 0) ./ 4.0);
    rawSignal = response + 0.03 .* sin(2*pi*0.7.*t);
    raw = table(t, command, response, rawSignal, ...
        'VariableNames', {'time_s', 'command', 'response', 'raw_signal'});
end

function dyDx = finiteDifference(x, y)
    % finiteDifference Compute dy/dx with NaN at the first sample.
    x = x(:);
    y = y(:);
    dx = [NaN; diff(x)];
    dy = [NaN; diff(y)];
    dyDx = dy ./ dx;
    dyDx(dx == 0) = NaN;
end

function tau = estimateTimeConstant(t, y)
    % estimateTimeConstant Estimate first-order time constant using 63.2% rise.
    % Caveat: assumes mostly monotonic step-like response.
    t = t(:);
    y = y(:);

    if numel(t) < 5 || all(isnan(y))
        tau = NaN;
        return;
    end

    y0 = y(1);
    tailStart = max(1, numel(y) - 10);
    yFinal = median(y(tailStart:end), "omitnan");
    dy = yFinal - y0;

    if abs(dy) < eps
        tau = NaN;
        return;
    end

    yTau = y0 + 0.632 * dy;
    if dy > 0
        idx = find(y >= yTau, 1, "first");
    else
        idx = find(y <= yTau, 1, "first");
    end

    if isempty(idx)
        tau = NaN;
    else
        tau = t(idx) - t(1);
    end
end

function applyTheme(fig, ax, theme)
    % applyTheme Apply a light or Halcyon dark theme to a figure/axes.
    theme = string(theme);
    if theme == "light"
        grid(ax, "on");
        return;
    end

    bg = [7, 9, 13] ./ 255;
    panel = [17, 21, 28] ./ 255;
    text = [242, 232, 213] ./ 255;
    brass = [184, 135, 70] ./ 255;
    gridColor = [107, 90, 58] ./ 255;

    fig.Color = bg;
    ax.Color = panel;
    ax.XColor = text;
    ax.YColor = text;
    ax.GridColor = gridColor;
    ax.GridAlpha = 0.28;
    ax.Box = "on";
    ax.LineWidth = 0.8;
    ax.Title.Color = text;
    ax.XLabel.Color = text;
    ax.YLabel.Color = text;

    % MATLAB axes do not expose each spine separately like Matplotlib.
    % XColor/YColor are the practical axis-line controls.
    ax.XColor = brass;
    ax.YColor = brass;

    lgd = legend(ax);
    if ~isempty(lgd)
        lgd.TextColor = text;
        lgd.Color = panel;
        lgd.EdgeColor = brass;
    end
end

function saveFigure(fig, figureDir, baseName, dpi)
    % saveFigure Save a figure as PNG and FIG.
    if nargin < 4
        dpi = 200;
    end
    ensureDir(figureDir);

    pngPath = fullfile(figureDir, baseName + ".png");
    figPath = fullfile(figureDir, baseName + ".fig");

    exportgraphics(fig, pngPath, "Resolution", dpi);
    savefig(fig, figPath);
    logMsg("OK", "Saved figure: " + string(pngPath));
end

function writeConfig(cfg)
    % writeConfig Save config as a readable text artifact.
    cfgPath = fullfile(cfg.logDir, "config_" + cfg.runId + ".txt");
    fid = fopen(cfgPath, "w");
    assert(fid > 0, "Could not open config file for writing: " + cfgPath);
    cleanupObj = onCleanup(@() fclose(fid)); %#ok<NASGU>

    fields = fieldnames(cfg);
    for i = 1:numel(fields)
        key = fields{i};
        value = cfg.(key);
        fprintf(fid, "%s = %s\n", key, stringifyValue(value));
    end

    logMsg("OK", "Wrote config: " + string(cfgPath));
end

function writeSummary(pathStr, cfg, metrics, processedPath, metricsPath)
    % writeSummary Save a compact analysis summary.
    fid = fopen(pathStr, "w");
    assert(fid > 0, "Could not open summary file for writing: " + pathStr);
    cleanupObj = onCleanup(@() fclose(fid)); %#ok<NASGU>

    fprintf(fid, "Project: %s\n", cfg.projectName);
    fprintf(fid, "Version: %s\n", cfg.version);
    fprintf(fid, "Run ID: %s\n", cfg.runId);
    fprintf(fid, "Input: %s\n", cfg.inputFile);
    fprintf(fid, "Processed table: %s\n", processedPath);
    fprintf(fid, "Metrics table: %s\n\n", metricsPath);

    fprintf(fid, "Metrics\n");
    fprintf(fid, "-------\n");

    fields = fieldnames(metrics);
    for i = 1:numel(fields)
        key = fields{i};
        value = metrics.(key);
        fprintf(fid, "%s: %s\n", key, stringifyValue(value));
    end
end

function escaped = escapeUnderscores(value)
    % escapeUnderscores Make labels display underscores literally.
    escaped = strrep(string(value), "_", "\_");
end

function s = stringifyValue(value)
    % stringifyValue Convert values to readable strings for logs.
    if isstring(value) || ischar(value)
        s = string(value);
    elseif isnumeric(value) || islogical(value)
        if isscalar(value)
            s = string(value);
        else
            s = string(mat2str(value));
        end
    else
        try
            s = string(value);
        catch
            s = "<unstringifiable>";
        end
    end
end
