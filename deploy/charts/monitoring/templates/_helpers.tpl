{{- define "feedback-hub-monitoring.prometheus" -}}
feedback-hub-prometheus
{{- end }}

{{- define "feedback-hub-monitoring.grafana" -}}
feedback-hub-grafana
{{- end }}

{{- define "feedback-hub-monitoring.loki" -}}
feedback-hub-loki
{{- end }}

{{- define "feedback-hub-monitoring.alloy" -}}
feedback-hub-alloy
{{- end }}

{{- define "feedback-hub-monitoring.tempo" -}}
feedback-hub-tempo
{{- end }}

{{- define "feedback-hub-monitoring.alertmanager" -}}
feedback-hub-alertmanager
{{- end }}

{{- define "feedback-hub-monitoring.alertEmailRequired" -}}
{{- $email := .Values.alertEmail -}}
{{- if or (not $email.to) (not $email.from) (not $email.user) (not $email.host) (not $email.smtpPort) (not $email.existingSecret) (not $email.passwordKey) -}}
{{- fail "alertEmail requires to, from, user, host, smtpPort, existingSecret, and passwordKey." -}}
{{- end -}}
{{- end }}

{{/* Call with (list $ "component-name"). */}}
{{- define "feedback-hub-monitoring.labels" -}}
{{- $root := index . 0 -}}
app.kubernetes.io/name: {{ index . 1 }}
app.kubernetes.io/instance: {{ $root.Release.Name }}
app.kubernetes.io/part-of: {{ $root.Chart.Name }}
app.kubernetes.io/managed-by: {{ $root.Release.Service }}
{{- end }}

{{- define "feedback-hub-monitoring.selectorLabels" -}}
{{- $root := index . 0 -}}
app.kubernetes.io/name: {{ index . 1 }}
app.kubernetes.io/instance: {{ $root.Release.Name }}
{{- end }}

{{/* Call with an image block from values. */}}
{{- define "feedback-hub-monitoring.image" -}}
{{- if .digest }}
{{- printf "%s@%s" .repository .digest }}
{{- else if or (not .tag) (eq .tag "latest") }}
{{- fail "Set image.digest or an immutable image.tag. Do not use latest." }}
{{- else }}
{{- printf "%s:%s" .repository .tag }}
{{- end }}
{{- end }}
