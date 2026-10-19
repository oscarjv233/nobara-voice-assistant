package conversations

import (
	"bufio"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"nobara-voice-assistant/internal/config"
)

var (
	reMetadata      = regexp.MustCompile(`(?s)<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>`)
	reSettings      = regexp.MustCompile(`(?s)<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>`)
	reSystemMsg     = regexp.MustCompile(`(?s)<SYSTEM_MESSAGE>.*?</SYSTEM_MESSAGE>`)
	reUserRequest   = regexp.MustCompile(`(?s)<USER_REQUEST>\s*(.*?)\s*(?:</USER_REQUEST>|$)`)
	reVoiceQuotes   = regexp.MustCompile(`(?i)(?:Instrucci[oó]n de voz|User voice instruction)[^:]*:\s*['"` + "`" + `]([^'"` + "`" + `]+)['"` + "`" + `]`)
	reRulesTrailing = regexp.MustCompile(`(?is)(?:MANDATORY RULES|REGLAS OBLIGATORIAS|Si te pide realizar una acci[oó]n).*$`)
	reXMLTags       = regexp.MustCompile(`<[^>]+>`)
)

// CleanUserText extracts clean user voice query from AGY wrapped prompt.
func CleanUserText(raw string) string {
	if raw == "" {
		return ""
	}
	s := reMetadata.ReplaceAllString(raw, "")
	s = reSettings.ReplaceAllString(s, "")
	s = reSystemMsg.ReplaceAllString(s, "")

	if m := reUserRequest.FindStringSubmatch(s); len(m) > 1 {
		s = m[1]
	}
	if m := reVoiceQuotes.FindStringSubmatch(s); len(m) > 1 {
		return strings.TrimSpace(m[1])
	}
	s = reRulesTrailing.ReplaceAllString(s, "")
	s = reXMLTags.ReplaceAllString(s, "")
	return strings.TrimSpace(s)
}

// Summary represents an overview of a conversation session.
type Summary struct {
	ID        string  `json:"id"`
	DateStr   string  `json:"date_str"`
	Timestamp float64 `json:"timestamp"`
	TurnCount int     `json:"turn_count"`
	Title     string  `json:"title"`
	LastReply string  `json:"last_reply"`
	IsActive  bool    `json:"is_active"`
}

// Action represents a tool call executed during a turn.
type Action struct {
	Name    string `json:"name"`
	Cmd     string `json:"cmd"`
	Summary string `json:"summary"`
}

// Turn represents a single request-response exchange.
type Turn struct {
	User    string   `json:"user"`
	Time    string   `json:"time"`
	Actions []Action `json:"actions"`
	Reply   string   `json:"reply"`
	RawUser string   `json:"raw_user,omitempty"`
}

// Detail contains complete conversation history and summary.
type Detail struct {
	ID      string        `json:"id"`
	Title   string        `json:"title"`
	Turns   []Turn        `json:"turns"`
	Summary DetailSummary `json:"summary"`
}

// DetailSummary provides high-level executive metrics for a session.
type DetailSummary struct {
	ToolsUsed []string `json:"tools_used"`
	LastUser  string   `json:"last_user"`
	LastReply string   `json:"last_reply"`
}

// GetDetail retrieves full turns and computes executive summary for conversation ID.
func GetDetail(convID string) (*Detail, error) {
	turns, err := GetTurns(convID)
	if err != nil {
		return nil, err
	}

	title := fmt.Sprintf("Conversación %s", convID[:8])
	if len(turns) > 0 && turns[0].User != "" {
		title = turns[0].User
	}

	toolSet := make(map[string]bool)
	var toolsUsed []string
	lastUser := ""
	lastReply := ""

	for _, turn := range turns {
		if turn.User != "" {
			lastUser = turn.User
		}
		if turn.Reply != "" {
			lastReply = turn.Reply
		}
		for _, act := range turn.Actions {
			if act.Name != "" && !toolSet[act.Name] {
				toolSet[act.Name] = true
				toolsUsed = append(toolsUsed, act.Name)
			}
		}
	}

	return &Detail{
		ID:    convID,
		Title: title,
		Turns: turns,
		Summary: DetailSummary{
			ToolsUsed: toolsUsed,
			LastUser:  lastUser,
			LastReply: lastReply,
		},
	}, nil
}


func getBrainDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".gemini", "antigravity-cli", "brain")
}

// List returns all conversation summaries sorted by modification time descending.
func List(activeConvID string, limit int) ([]Summary, error) {
	brainDir := getBrainDir()
	entries, err := os.ReadDir(brainDir)
	if err != nil {
		return nil, err
	}

	type dirMeta struct {
		name    string
		modTime time.Time
	}
	var dirs []dirMeta
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		dirs = append(dirs, dirMeta{name: e.Name(), modTime: info.ModTime()})
	}

	sort.Slice(dirs, func(i, j int) bool {
		return dirs[i].modTime.After(dirs[j].modTime)
	})

	if limit > 0 && len(dirs) > limit {
		dirs = dirs[:limit]
	}

	var results []Summary
	for _, d := range dirs {
		convID := d.name
		transcriptPath := filepath.Join(brainDir, convID, ".system_generated", "logs", "transcript.jsonl")
		fi, err := os.Stat(transcriptPath)
		if err != nil {
			continue
		}

		mtime := fi.ModTime()
		dateStr := mtime.Format("02/01/2006 15:04:05")

		firstPrompt := ""
		lastReply := ""
		turnCount := 0

		file, err := os.Open(transcriptPath)
		if err != nil {
			continue
		}

		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" {
				continue
			}

			var entry map[string]interface{}
			if err := json.Unmarshal([]byte(line), &entry); err != nil {
				continue
			}

			etype, _ := entry["type"].(string)
			content, _ := entry["content"].(string)

			if etype == "USER_INPUT" {
				turnCount++
				if firstPrompt == "" {
					firstPrompt = CleanUserText(content)
				}
			} else if etype == "PLANNER_RESPONSE" && content != "" {
				lastReply = strings.TrimSpace(content)
			}
		}
		file.Close()

		if turnCount == 0 && firstPrompt == "" {
			continue
		}

		title := firstPrompt
		if title == "" {
			title = fmt.Sprintf("Conversación %s", convID[:8])
		}

		if len(lastReply) > 120 {
			lastReply = lastReply[:120] + "..."
		}

		results = append(results, Summary{
			ID:        convID,
			DateStr:   dateStr,
			Timestamp: float64(mtime.UnixNano()) / 1e9,
			TurnCount: turnCount,
			Title:     title,
			LastReply: lastReply,
			IsActive:  (convID == activeConvID),
		})
	}

	return results, nil
}

// GetTurns parses turn-by-turn history of a specific conversation ID.
func GetTurns(convID string) ([]Turn, error) {
	transcriptPath := filepath.Join(getBrainDir(), convID, ".system_generated", "logs", "transcript.jsonl")
	file, err := os.Open(transcriptPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var turns []Turn
	var currentTurn *Turn

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		var entry map[string]interface{}
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			continue
		}

		etype, _ := entry["type"].(string)
		content, _ := entry["content"].(string)
		createdAt, _ := entry["created_at"].(string)

		timeStr := ""
		if createdAt != "" {
			if t, err := time.Parse(time.RFC3339, createdAt); err == nil {
				timeStr = t.Local().Format("15:04:05")
			} else {
				timeStr = createdAt
			}
		}

		if etype == "USER_INPUT" {
			turn := Turn{
				User:    CleanUserText(content),
				Time:    timeStr,
				Actions: []Action{},
				Reply:   "",
				RawUser: content,
			}
			turns = append(turns, turn)
			currentTurn = &turns[len(turns)-1]
		} else if currentTurn != nil {
			if tcList, ok := entry["tool_calls"].([]interface{}); ok {
				for _, rawTC := range tcList {
					if tc, ok := rawTC.(map[string]interface{}); ok {
						name, _ := tc["name"].(string)
						var cmdStr, summaryStr string
						if args, ok := tc["args"].(map[string]interface{}); ok {
							cmdStr, _ = args["CommandLine"].(string)
							summaryStr, _ = args["toolSummary"].(string)
						}
						currentTurn.Actions = append(currentTurn.Actions, Action{
							Name:    name,
							Cmd:     cmdStr,
							Summary: summaryStr,
						})
					}
				}
			}
			if etype == "PLANNER_RESPONSE" && content != "" {
				currentTurn.Reply = strings.TrimSpace(content)
			}
		}
	}

	return turns, scanner.Err()
}

// GenerateUUID creates a random UUID v4 string.
func GenerateUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%s-%s-%s-%s-%s",
		hex.EncodeToString(b[0:4]),
		hex.EncodeToString(b[4:6]),
		hex.EncodeToString(b[6:8]),
		hex.EncodeToString(b[8:10]),
		hex.EncodeToString(b[10:16]),
	)
}

// ResetActiveSession generates a new UUID and updates ACTIVE_CONVERSATION_ID in config.env.
func ResetActiveSession(projectDir string) (string, error) {
	newID := GenerateUUID()
	configPath := filepath.Join(projectDir, "config", "config.env")
	err := config.UpdateValue(configPath, "ACTIVE_CONVERSATION_ID", newID)
	return newID, err
}

// Delete removes a conversation directory from disk.
func Delete(convID string) error {
	convDir := filepath.Join(getBrainDir(), convID)
	return os.RemoveAll(convDir)
}

// ExportMarkdown formats conversation turns into readable markdown document.
func ExportMarkdown(convID string) (string, error) {
	turns, err := GetTurns(convID)
	if err != nil {
		return "", err
	}

	title := fmt.Sprintf("Conversación %s", convID[:8])
	if len(turns) > 0 && turns[0].User != "" {
		title = turns[0].User
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("# Conversación Jarvis: %s\n\n", title))
	sb.WriteString(fmt.Sprintf("- ID de Sesión: `%s`\n", convID))
	sb.WriteString(fmt.Sprintf("- Total de Turnos: %d\n\n---\n\n", len(turns)))

	for i, turn := range turns {
		timeTag := ""
		if turn.Time != "" {
			timeTag = fmt.Sprintf(" (%s)", turn.Time)
		}
		sb.WriteString(fmt.Sprintf("### Turno %d%s\n", i+1, timeTag))
		sb.WriteString(fmt.Sprintf("**Usuario:**\n%s\n\n", turn.User))

		if len(turn.Actions) > 0 {
			sb.WriteString("**Herramientas ejecutadas:**\n")
			for _, act := range turn.Actions {
				detail := act.Summary
				if detail == "" {
					detail = act.Cmd
				}
				sb.WriteString(fmt.Sprintf("- `%s`: %s\n", act.Name, detail))
			}
			sb.WriteString("\n")
		}

		if turn.Reply != "" {
			sb.WriteString(fmt.Sprintf("**Jarvis:**\n%s\n\n", turn.Reply))
		}
		sb.WriteString("---\n\n")
	}

	return sb.String(), nil
}
