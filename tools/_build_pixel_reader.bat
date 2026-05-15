@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
cl /nologo /EHsc /std:c++17 /W3 ^
    /I"..\build\cp314-cp314-win_amd64\decklink_generated" ^
    pixel_reader.cpp ^
    "..\build\cp314-cp314-win_amd64\decklink_generated\DeckLinkAPI_i.c" ^
    /Fe:pixel_reader.exe ^
    /link ole32.lib oleaut32.lib comsuppw.lib
