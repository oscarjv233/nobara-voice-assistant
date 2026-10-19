package fastpath

import (
	"fmt"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Result holds fast-path execution feedback.
type Result struct {
	Handled bool   `json:"handled"`
	Title   string `json:"title,omitempty"`
	Reply   string `json:"reply,omitempty"`
}

var (
	reVolumeSet = regexp.MustCompile(`(?:volumen al|pon el volumen al|volumen en|set volume to)\s+(\d{1,3})%?`)
	reSensorGPU = regexp.MustCompile(`(?i)(?:edge|junction|temp1):\s+\+([0-9\.]+)°C`)
	reSensorCPU = regexp.MustCompile(`(?i)(?:Package id 0|Tctl|CPU|temp1):\s+\+([0-9\.]+)°C`)
	reWpVolume  = regexp.MustCompile(`Volume:\s+([0-9\.]+)`)
)

// normalizeText strips accents and converts text to lowercase for intent matching.
func normalizeText(input string) string {
	s := strings.ToLower(strings.TrimSpace(input))
	replacements := []struct {
		old, new string
	}{
		{"á", "a"}, {"é", "e"}, {"í", "i"}, {"ó", "o"}, {"ú", "u"},
	}
	for _, r := range replacements {
		s = strings.ReplaceAll(s, r.old, r.new)
	}
	return s
}

func runCmd(name string, args ...string) string {
	out, err := exec.Command(name, args...).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func getCurrentVolume() int {
	out := runCmd("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
	m := reWpVolume.FindStringSubmatch(out)
	if len(m) > 1 {
		if val, err := strconv.ParseFloat(m[1], 64); err == nil {
			return int(val*100 + 0.5)
		}
	}
	return 50
}

func controlMPRIS(action string) bool {
	// Try playerctl first
	if _, err := exec.LookPath("playerctl"); err == nil {
		actionMap := map[string]string{
			"PlayPause": "play-pause",
			"Next":      "next",
			"Previous":  "previous",
			"Stop":      "stop",
			"Play":      "play",
			"Pause":     "pause",
		}
		if act, ok := actionMap[action]; ok {
			if err := exec.Command("playerctl", act).Run(); err == nil {
				return true
			}
		}
	}

	// Fallback to qdbus
	out := runCmd("qdbus")
	lines := strings.Split(out, "\n")
	var success bool
	for _, line := range lines {
		service := strings.TrimSpace(line)
		if strings.Contains(service, "org.mpris.MediaPlayer2") {
			cmd := exec.Command("qdbus", service, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player."+action)
			if err := cmd.Run(); err == nil {
				success = true
			}
		}
	}
	return success
}

func getHardwareStatus(lang string) string {
	out := runCmd("sensors")
	var gpuTemp, cpuTemp int
	var hasGPU, hasCPU bool

	mGPU := reSensorGPU.FindStringSubmatch(out)
	if len(mGPU) > 1 {
		if v, err := strconv.ParseFloat(mGPU[1], 64); err == nil {
			gpuTemp = int(v)
			hasGPU = true
		}
	}

	mCPU := reSensorCPU.FindStringSubmatch(out)
	if len(mCPU) > 1 {
		if v, err := strconv.ParseFloat(mCPU[1], 64); err == nil {
			cpuTemp = int(v)
			hasCPU = true
		}
	}

	if lang == "en" {
		var parts []string
		if hasGPU {
			parts = append(parts, fmt.Sprintf("GPU is at %d degrees", gpuTemp))
		}
		if hasCPU {
			parts = append(parts, fmt.Sprintf("CPU is at %d degrees", cpuTemp))
		}
		if len(parts) > 0 {
			return strings.Join(parts, ". ") + "."
		}
		return "Hardware sensors are operating within normal limits."
	}

	var parts []string
	if hasGPU {
		parts = append(parts, fmt.Sprintf("La gráfica está a %d grados", gpuTemp))
	}
	if hasCPU {
		parts = append(parts, fmt.Sprintf("la CPU a %d grados", cpuTemp))
	}
	if len(parts) > 0 {
		return strings.Join(parts, " y ") + "."
	}
	return "Los sensores de hardware están en rangos normales."
}

// GetHardwareMetrics returns GPU temperature, CPU temperature, PipeWire volume, and summary text.
func GetHardwareMetrics(lang string) (gpuTemp, cpuTemp, volume int, summary string) {
	out := runCmd("sensors")
	var hasGPU, hasCPU bool

	mGPU := reSensorGPU.FindStringSubmatch(out)
	if len(mGPU) > 1 {
		if v, err := strconv.ParseFloat(mGPU[1], 64); err == nil {
			gpuTemp = int(v)
			hasGPU = true
		}
	}

	mCPU := reSensorCPU.FindStringSubmatch(out)
	if len(mCPU) > 1 {
		if v, err := strconv.ParseFloat(mCPU[1], 64); err == nil {
			cpuTemp = int(v)
			hasCPU = true
		}
	}

	volume = getCurrentVolume()
	summary = getHardwareStatus(lang)

	if !hasGPU && !hasCPU {
		gpuTemp = 0
		cpuTemp = 0
	}
	return gpuTemp, cpuTemp, volume, summary
}

// TryMatch executes fast path commands if voice text matches predefined local intents.

func TryMatch(text, lang string) Result {
	clean := normalizeText(text)
	isEN := (lang == "en")

	// 1. Hardware Status
	hwQueries := []string{
		"como va la grafica", "temperatura de la grafica", "como va el pc",
		"como va el ordenador", "temperatura del ordenador", "estado del hardware",
		"gpu temp", "hardware status", "how is the gpu", "temperature of the pc",
	}
	for _, q := range hwQueries {
		if strings.Contains(clean, q) {
			title := "Estado del Hardware"
			if isEN {
				title = "Hardware Status"
			}
			return Result{Handled: true, Title: title, Reply: getHardwareStatus(lang)}
		}
	}

	// 2. Media Controls
	nextQueries := []string{
		"siguiente cancion", "pasa de cancion", "pasa la cancion", "pasa la musica",
		"salta de cancion", "next song", "next track", "skip song",
	}
	for _, q := range nextQueries {
		if strings.Contains(clean, q) {
			controlMPRIS("Next")
			reply := "Siguiente canción."
			if isEN {
				reply = "Next track."
			}
			return Result{Handled: true, Title: "Multimedia", Reply: reply}
		}
	}

	prevQueries := []string{
		"cancion anterior", "anterior cancion", "cancion previa",
		"previous song", "previous track",
	}
	for _, q := range prevQueries {
		if strings.Contains(clean, q) {
			controlMPRIS("Previous")
			reply := "Canción anterior."
			if isEN {
				reply = "Previous track."
			}
			return Result{Handled: true, Title: "Multimedia", Reply: reply}
		}
	}

	stopQueries := []string{
		"para la musica", "parar musica", "detener musica", "stop music", "stop media",
	}
	for _, q := range stopQueries {
		if strings.Contains(clean, q) {
			controlMPRIS("Stop")
			reply := "Música detenida."
			if isEN {
				reply = "Music stopped."
			}
			return Result{Handled: true, Title: "Multimedia", Reply: reply}
		}
	}

	resumeQueries := []string{
		"reanuda la musica", "reanudar musica", "continua la musica",
		"resume music", "play music", "reproducir musica",
	}
	for _, q := range resumeQueries {
		if strings.Contains(clean, q) {
			controlMPRIS("Play")
			reply := "Reproduciendo música."
			if isEN {
				reply = "Playing music."
			}
			return Result{Handled: true, Title: "Multimedia", Reply: reply}
		}
	}

	pauseQueries := []string{
		"pausa la musica", "pausar musica", "pausa el video", "pausar el video",
		"pause music", "pause video", "play pause", "pausa", "pausar", "pause",
	}
	for _, q := range pauseQueries {
		if strings.Contains(clean, q) {
			controlMPRIS("PlayPause")
			reply := "Música pausada."
			if isEN {
				reply = "Music paused."
			}
			return Result{Handled: true, Title: "Multimedia", Reply: reply}
		}
	}

	// 3. Volume and Mute Controls
	if m := reVolumeSet.FindStringSubmatch(clean); len(m) > 1 {
		if val, err := strconv.Atoi(m[1]); err == nil {
			if val < 0 {
				val = 0
			}
			if val > 100 {
				val = 100
			}
			decimalVal := fmt.Sprintf("%.2f", float64(val)/100.0)
			_ = exec.Command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", decimalVal).Run()

			title := "Volumen"
			reply := fmt.Sprintf("Volumen ajustado al %d%%.", val)
			if isEN {
				title = "Volume"
				reply = fmt.Sprintf("Volume set to %d%%.", val)
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	volUpQueries := []string{
		"sube el volumen", "subir volumen", "mas volumen", "subelo",
		"volume up", "increase volume", "louder",
	}
	for _, q := range volUpQueries {
		if strings.Contains(clean, q) {
			_ = exec.Command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+").Run()
			cur := getCurrentVolume()
			title := "Volumen"
			reply := fmt.Sprintf("Volumen subido al %d%%.", cur)
			if isEN {
				title = "Volume"
				reply = fmt.Sprintf("Volume set to %d%%.", cur)
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	volDownQueries := []string{
		"baja el volumen", "bajar volumen", "menos volumen", "bajalo",
		"volume down", "decrease volume", "quieter",
	}
	for _, q := range volDownQueries {
		if strings.Contains(clean, q) {
			_ = exec.Command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-").Run()
			cur := getCurrentVolume()
			title := "Volumen"
			reply := fmt.Sprintf("Volumen bajado al %d%%.", cur)
			if isEN {
				title = "Volume"
				reply = fmt.Sprintf("Volume set to %d%%.", cur)
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	muteAudioQueries := []string{
		"silencia el audio", "silenciar audio", "silencia el sonido", "mute audio",
		"desmutea", "quitar silencio", "unmute", "silencio", "mute",
	}
	for _, q := range muteAudioQueries {
		if strings.Contains(clean, q) {
			_ = exec.Command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle").Run()
			title := "Audio"
			reply := "Audio silenciado o activado."
			if isEN {
				reply = "Audio mute toggled."
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	muteMicQueries := []string{
		"silencia el microfono", "silencia el micro", "silenciar microfono",
		"mute mic", "mute microphone", "unmute mic",
	}
	for _, q := range muteMicQueries {
		if strings.Contains(clean, q) {
			_ = exec.Command("wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle").Run()
			title := "Micrófono"
			reply := "Micrófono silenciado o activado."
			if isEN {
				title = "Microphone"
				reply = "Microphone mute toggled."
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	// 4. Quick System Actions
	lockQueries := []string{
		"bloquea la pantalla", "bloquear pantalla", "bloquear sesion",
		"lock screen", "lock session",
	}
	for _, q := range lockQueries {
		if strings.Contains(clean, q) {
			_ = exec.Command("loginctl", "lock-session").Run()
			title := "Sistema"
			reply := "Pantalla bloqueada."
			if isEN {
				title = "System"
				reply = "Screen locked."
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	timeQueries := []string{"que hora es", "dime la hora", "what time is it"}
	for _, q := range timeQueries {
		if strings.Contains(clean, q) {
			now := time.Now()
			title := "Hora"
			reply := fmt.Sprintf("Son las %02d:%02d.", now.Hour(), now.Minute())
			if isEN {
				title = "Time"
				reply = fmt.Sprintf("It is %02d:%02d.", now.Hour(), now.Minute())
			}
			return Result{Handled: true, Title: title, Reply: reply}
		}
	}

	dateQueries := []string{"que dia es hoy", "que fecha es hoy", "what date is today", "what day is today"}
	for _, q := range dateQueries {
		if strings.Contains(clean, q) {
			now := time.Now()
			title := "Fecha"
			if isEN {
				title = "Date"
				return Result{Handled: true, Title: title, Reply: fmt.Sprintf("Today is %s, %s %d.", now.Weekday().String(), now.Month().String(), now.Day())}
			}
			dias := []string{"domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"}
			meses := []string{"enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"}
			return Result{
				Handled: true,
				Title:   title,
				Reply:   fmt.Sprintf("Hoy es %s, %d de %s.", dias[int(now.Weekday())], now.Day(), meses[int(now.Month())-1]),
			}
		}
	}

	return Result{Handled: false}
}
