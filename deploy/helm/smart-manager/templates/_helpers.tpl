{{/* Nombre base del release */}}
{{- define "smart-manager.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "smart-manager.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "smart-manager.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Etiquetas comunes */}}
{{- define "smart-manager.labels" -}}
app.kubernetes.io/name: {{ include "smart-manager.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
app.kubernetes.io/part-of: smart-manager-ai
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "smart-manager.selectorLabels" -}}
app.kubernetes.io/name: {{ include "smart-manager.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end -}}

{{/* Nombre del Secret a usar: el existente o el generado por el chart */}}
{{- define "smart-manager.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{ .Values.secrets.existingSecret }}
{{- else -}}
{{ include "smart-manager.fullname" . }}-secrets
{{- end -}}
{{- end -}}
