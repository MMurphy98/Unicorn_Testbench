import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { Workbook } from "@oai/artifact-tool";

const buildDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(buildDir);
const payload = JSON.parse(await fs.readFile(path.join(buildDir, "prepared_rows.json"), "utf8"));
const matrix = [payload.fields, ...payload.rows];
assert.equal(matrix.length, 6001);
assert.equal(payload.fields.length, 12);

// Keep original ISO text separately: this runtime infers JS Date even on CSV
// import. Restore the original text on export to preserve sub-ms precision.
const sourceCsv = matrix.map(row => row.map(csvField).join(",")).join("\r\n") + "\r\n";
const workbook = await Workbook.fromCSV(sourceCsv, {sheetName:"DMM readings"});
const sheet = workbook.worksheets.getItem("DMM readings");
sheet.showGridLines = false;
const all = sheet.getRangeByIndexes(0, 0, matrix.length, payload.fields.length);
for (const col of [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]) {
  sheet.getRangeByIndexes(1, col, payload.rows.length, 1).values = payload.rows.map(row => [row[col]]);
}
console.log("Loaded 6000 measurement rows.");
const previewCells = sheet.getRange("A1:L7");
previewCells.format.font = { name: "Arial", size: 11 };
previewCells.format.rowHeight = 21;
previewCells.format.columnWidth = 24;
sheet.getRange("A1:D7").format.columnWidth = 19;
sheet.getRange("F1:F7").format.columnWidth = 40;
sheet.getRange("L1:L7").format.columnWidth = 49;
sheet.getRange("A1:L1").format.fill = "#E8EEF5";
sheet.getRange("A1:L1").format.font.bold = true;
sheet.getRange("A1:L1").format.wrapText = true;
sheet.getRange("A1:L1").format.rowHeight = 60;
sheet.getRange("A2:D7").setNumberFormat("0");
sheet.getRange("E2:E7").setNumberFormat("0.000000");
sheet.getRange("G2:H7").setNumberFormat("0.000000000000E+00");
sheet.getRange("I2:I7").setNumberFormat("0.000000000000");
sheet.getRange("J2:K7").setNumberFormat("0");
sheet.freezePanes.freezeRows(1);
workbook.recalculate();
console.log("Finished preview formatting and recalculation.");

// Export underlying typed values, not display-formatted cells. JS number strings
// preserve the full binary64 value when parsed back by standard CSV readers.
const values = [];
for (let start = 0; start < matrix.length; start += 250) {
  const count = Math.min(250, matrix.length - start);
  const block = sheet.getRangeByIndexes(start, 0, count, payload.fields.length).values;
  for (let row = 0; row < count; row++) {
    for (let col = 0; col < payload.fields.length; col++) {
      if (col === 5 && start + row > 0 && block[row][col] instanceof Date) {
        assert.equal(block[row][col].getTime(), Date.parse(matrix[start + row][col]), "Timestamp row alignment");
        block[row][col] = matrix[start + row][col];
      }
      assert.equal(block[row][col], matrix[start + row][col], `Row ${start+row}, column ${payload.fields[col]}`);
    }
  }
  values.push(...block);
}
console.log("Verified all underlying values in bounded blocks.");
function csvField(value) {
  const text = String(value);
  return /[,"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
const output = "\uFEFF" + values.map(row => row.map(csvField).join(",")).join("\r\n") + "\r\n";
const csvPath = path.join(root, "chip1_chip3_dmm_readings_20260918.csv");
await fs.writeFile(csvPath, output, "utf8");
console.log(JSON.stringify({csv:csvPath, dataRows:values.length-1, columns:payload.fields.length, encoding:"UTF-8 with BOM", numericEncoding:"Full-precision round-trip binary64", bytes:Buffer.byteLength(output,"utf8")}));
// The presentation-only UTC prefix prevents this renderer's date coercion.
// The delivered CSV above contains the original ISO text without this prefix.
sheet.getRange("F2:F7").values = payload.rows.slice(0, 6).map(row => [`UTC ${row[5]}`]);
sheet.getRange("F1:F7").format.columnWidth = 48;
sheet.getRange("G1:I7").format.columnWidth = 29;
for (let row=0; row<6; row++) {
  assert.equal(sheet.getRange("F2:F7").values[row][0], `UTC ${payload.rows[row][5]}`);
}
workbook.recalculate();
console.log((await workbook.inspect({kind:"region", sheetId:sheet.name, range:"A1:I4", maxChars:1500, tableMaxRows:4, tableMaxCols:9})).ndjson);
const preview = await workbook.render({sheetName:"DMM readings", range:"A1:I7", scale:1.3, format:"png"});
await fs.writeFile(path.join(buildDir, "csv_preview.png"), new Uint8Array(await preview.arrayBuffer()));
console.log("Saved bounded preview.");
