{{/*
Expand the name of the chart.
*/}}
{{- define "chenxu.name" -}}
{{- .Chart.Name }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "chenxu.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "chenxu.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "chenxu.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "chenxu.selectorLabels" -}}
app.kubernetes.io/name: {{ include "chenxu.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
