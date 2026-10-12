{{- define "feedback-hub-litellm.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "feedback-hub-litellm.labels" -}}
app.kubernetes.io/name: {{ include "feedback-hub-litellm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "feedback-hub-litellm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "feedback-hub-litellm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "feedback-hub-litellm.image" -}}
{{- if .Values.image.digest }}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest }}
{{- else if or (not .Values.image.tag) (eq .Values.image.tag "latest") }}
{{- fail "Set image.digest or an immutable image.tag. Do not use latest." }}
{{- else }}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag }}
{{- end }}
{{- end }}
