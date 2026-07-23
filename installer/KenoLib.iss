; ============================================================================
;  KenoLib - script Inno Setup pentru installerul Windows (KenoLib-Setup.exe)
; ----------------------------------------------------------------------------
;  Impacheteaza rezultatul PyInstaller (dist\KenoLib) intr-un singur fisier
;  de instalare. Aplicatia are Python-ul si toate bibliotecile incluse, deci
;  pe calculatorul pe care se instaleaza NU trebuie instalat nimic altceva.
;
;  Nu edita/compila manual acest fisier -- ruleaza make_installer.bat, care
;  construieste intai executabilul, se asigura ca Inno Setup e prezent si
;  apoi compileaza acest script.
; ============================================================================

#define AppName "KenoLib"
#define AppVersion "1.0.0"
#define AppPublisher "KenoLib"
#define AppExeName "KenoLib.exe"

[Setup]
; AppId identifica unic aplicatia pentru upgrade/dezinstalare -- NU-l schimba
; intre versiuni, altfel Windows ar trata versiunea noua ca un program diferit.
AppId={{7E1B2C3D-9A45-4C6E-8B21-1F5D7E9A0B34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
; Instalare per-utilizator (fara drepturi de administrator / fara prompt UAC),
; dar daca utilizatorul ARE drepturi de admin poate alege instalarea pentru
; toti utilizatorii din dialogul afisat.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=KenoLib-Setup
SetupIconFile=..\app_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
; Imagini de brand in expert (generate cu generate_installer_images.py).
; Fiecare are doua marimi -- Inno o alege pe cea potrivita rezolutiei ecranului.
WizardImageFile=assets\wizard-large.bmp,assets\wizard-large-2x.bmp
WizardSmallImageFile=assets\wizard-small.bmp,assets\wizard-small-2x.bmp
; Datele utilizatorului (catalogul) stau in %LOCALAPPDATA%\KenoLib si NU sunt
; atinse la dezinstalare -- avertizam ca dezinstalarea nu sterge biblioteca.

[Languages]
Name: "ro"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Intreg folderul produs de PyInstaller (executabil + _internal cu Python si
; bibliotecile). recursesubdirs/createallsubdirs pastreaza structura interna.
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; ----------------------------------------------------------------------------
;  Mesaje in limba romana (peste baza engleza Default.isl). Doar sirurile cele
;  mai vizibile -- restul (rare) raman pe engleza, fara efect asupra folosirii.
; ----------------------------------------------------------------------------
[Messages]
SetupWindowTitle=Instalare — %1
SetupAppTitle=Instalare {#AppName}
; Butoane
ButtonBack=< Îna&poi
ButtonNext=&Următorul >
ButtonInstall=&Instalează
ButtonCancel=Anulează
ButtonFinish=&Finalizează
ButtonBrowse=&Răsfoiește...
ButtonYes=&Da
ButtonNo=&Nu
; Pagina de bun venit
WelcomeLabel1=Bine ați venit la instalarea aplicației [name]
WelcomeLabel2=Acest program va instala [name/ver] pe calculatorul dumneavoastră.%n%nSe recomandă închiderea celorlalte aplicații înainte de a continua.
ClickNext=Apăsați „Următorul” pentru a continua sau „Anulează” pentru a ieși.
; Alegerea folderului
WizardSelectDir=Alegeți locația de instalare
SelectDirDesc=Unde doriți să fie instalat [name]?
SelectDirLabel3=Programul va instala [name] în folderul de mai jos.
SelectDirBrowseLabel=Pentru a continua, apăsați „Următorul”. Pentru a alege alt folder, apăsați „Răsfoiește”.
DiskSpaceGBLabel=Este necesar cel puțin [gb] GB de spațiu liber pe disc.
DiskSpaceMBLabel=Sunt necesari cel puțin [mb] MB de spațiu liber pe disc.
CannotInstallToNetworkDrive=Instalarea pe o unitate de rețea nu este acceptată.
; Meniul Start
WizardSelectComponents=Alegeți componentele
WizardSelectTasks=Selectați activitățile suplimentare
SelectTasksDesc=Ce activități suplimentare doriți să fie efectuate?
SelectTasksLabel2=Selectați activitățile suplimentare pentru instalarea [name], apoi apăsați „Următorul”.
SelectStartMenuFolderDesc=Unde doriți să fie plasate scurtăturile aplicației?
SelectStartMenuFolderLabel3=Programul va crea scurtăturile în folderul de mai jos din meniul Start.
; Gata de instalare
WizardReady=Gata de instalare
ReadyLabel1=Programul este gata să instaleze [name] pe calculatorul dumneavoastră.
ReadyLabel2a=Apăsați „Instalează” pentru a continua sau „Înapoi” pentru a modifica setările.
; Instalare in curs
WizardInstalling=Se instalează
InstallingLabel=Vă rugăm să așteptați cât timp [name] se instalează pe calculatorul dumneavoastră.
; Finalizare
FinishedHeadingLabel=Instalarea [name] s-a încheiat
FinishedLabelNoIcons=Programul a terminat instalarea [name] pe calculatorul dumneavoastră.
FinishedLabel=Programul a terminat instalarea [name]. Aplicația poate fi pornită folosind scurtăturile create.
ClickFinish=Apăsați „Finalizează” pentru a închide programul de instalare.
RunEntryExec=Pornește [name]
; Anulare
ExitSetupTitle=Ieșire din instalare
ExitSetupMessage=Instalarea nu este completă. Dacă ieșiți acum, aplicația nu va fi instalată.%n%nSunteți sigur că doriți să ieșiți?
; Dezinstalare
ConfirmUninstall=Sunteți sigur că doriți să dezinstalați complet %1?%n%n(Catalogul bibliotecii și setările din folderul de date NU vor fi șterse.)
UninstallStatusLabel=Vă rugăm să așteptați cât timp %1 este dezinstalat de pe calculator.

[CustomMessages]
; ro (Default.isl e engleza) -> traducem cele patru mesaje standard folosite mai sus.
CreateDesktopIcon=Creează o scurtătură pe desktop
AdditionalIcons=Scurtături suplimentare:
UninstallProgram=Dezinstalează %1
LaunchProgram=Pornește %1
