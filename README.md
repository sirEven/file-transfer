# File Transfer
This is a small script to obvserve a source folder for new files (with watchdog) and transfer files to a remote destination when they show up fresh in the source folder. Once the script is done with a file, it is moved into the `transferred` subdirectory.

## Usage
1) Fill in all the required variables in the .env file
2) Either run the script normally with `python main.py` or instead...
3) ... Create your own daemon that runs this script in the background (starting with each OS startup). Here is an exemplary walkthrough for macOS: 

Replace `<username>` with your macOS username.
Replace `<python_path>` with the path to your Python 3 executable (run `which python3` to find it).
Replace `<project_path>` with the absolute path to the project directory (where you cloned it) (e.g., /Users/`<username>`/path/to/file-transfer).
Save the plist as ~/Library/LaunchAgents/com.`<username>`.filetransfer.plist.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.<username>.filetransfer</string>
    <key>ProgramArguments</key>
    <array>
        <string><python_path></string>
        <string><project_path>/main.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string><project_path></string>
    <key>StandardOutPath</key>
    <string><project_path>/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string><project_path>/logs/stderr.log</string>
</dict>
</plist>
```

4) run `launchctl load ~/Library/LaunchAgents/com.<username>.<filetransfer>.plist` in your Terminal (always replace `<username>` with your macOS username).
5) To check if your daemon is running, run `launchctl list | grep com.<username>.musictransfer` you should find smth along the lines of `23362	0	com.<username>.filetransfer` where the number will be your own version of PID and the following string represents the name of the process.

## Help
If you run into problems, a good starting point is to set debug to true in the .env file and have a look at log files in the logs directory of the project.
(Don't forget to turn off again afterwards, or else the daemon will slowly bloat those files and eat your storage...)
Each change you do, needs to follow by an unload and load of the daemon process again. 
To unload, run `launchctl unload ~/Library/LaunchAgents/com.<username>.musictransfer.plist` if you check again, you should _not_ see your previously found process anymore. 

## ATTENTION
This is neither maintained nor recommended. It is a simple script to automate ... some file management stuff - highly customized for my own use case. If by accident it helps somebody to achieve something that's a plus!
