# Record with scripts/demo.sh
Output docs/images/demo.gif

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 720
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 60ms

Hide
Type "cd /demo && rm -f *.srt && export PS1='$ ' && clear"
Enter
Show

Sleep 500ms
Type "ls"
Enter
Sleep 1500ms

Type "pgsrip rip -l en -l pt-BR media.mkv"
Sleep 500ms
Enter
Wait+Screen@120s /ripped from 1 file/
Sleep 1500ms

Type "ls"
Enter
Sleep 1500ms

Type "head -n 8 media.en.srt media.pt-BR.srt"
Enter
Sleep 5s
