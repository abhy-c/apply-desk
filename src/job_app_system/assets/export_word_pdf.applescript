on run argv
    if (count of argv) is not 2 then error "Expected input DOCX and output PDF paths"
    set inputPath to item 1 of argv
    set outputPath to item 2 of argv

    tell application "Microsoft Word"
        launch
        open file name inputPath read only true add to recent files false
        set resumeDoc to active document
        repaginate resumeDoc
        save as resumeDoc file name outputPath file format format PDF add to recent files false
        close resumeDoc saving no
    end tell

    return outputPath
end run
