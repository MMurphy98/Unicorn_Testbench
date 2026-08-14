function results = run_all_tests()
%RUN_ALL_TESTS Discover and run all MATLAB tests in this repository.

testDir = fileparts(mfilename("fullpath"));
matlabDir = fileparts(testDir);
sourceDir = fullfile(matlabDir, "src");

addpath(sourceDir);
pathCleanup = onCleanup(@() rmpath(sourceDir)); %#ok<NASGU>

suite = matlab.unittest.TestSuite.fromFolder( ...
    testDir, ...
    "IncludingSubfolders", true);
results = run(suite);

disp(table(results));
end
