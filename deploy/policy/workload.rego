package main

import rego.v1

containers contains container if {
	input.kind == "Deployment"
	container := input.spec.template.spec.containers[_]
}

containers contains container if {
	input.kind == "Deployment"
	container := input.spec.template.spec.initContainers[_]
}

containers contains container if {
	input.kind == "Deployment"
	container := input.spec.template.spec.ephemeralContainers[_]
}

deny contains msg if {
	input.kind == "Secret"
	msg := "Do not embed a Secret in the chart"
}

deny contains msg if {
	input.kind == "Deployment"
	input.spec.template.spec.hostNetwork == true
	msg := "hostNetwork is not allowed"
}

deny contains msg if {
	input.kind == "Deployment"
	not input.spec.template.spec.securityContext.runAsNonRoot == true
	msg := "The pod must set runAsNonRoot"
}

deny contains msg if {
	container := containers[_]
	container.securityContext.privileged == true
	msg := sprintf("%s is privileged", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.securityContext.allowPrivilegeEscalation == false
	msg := sprintf("%s must set allowPrivilegeEscalation to false", [container.name])
}

deny contains msg if {
	container := containers[_]
	security := object.get(container, "securityContext", {})
	capabilities := object.get(security, "capabilities", {})
	drop := object.get(capabilities, "drop", [])
	not "ALL" in drop
	msg := sprintf("%s must drop all capabilities", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.livenessProbe
	msg := sprintf("%s is missing a liveness probe", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.readinessProbe
	msg := sprintf("%s is missing a readiness probe", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.resources.requests.cpu
	msg := sprintf("%s is missing a CPU request", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.resources.limits.cpu
	msg := sprintf("%s is missing a CPU limit", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.resources.requests.memory
	msg := sprintf("%s is missing a memory request", [container.name])
}

deny contains msg if {
	container := containers[_]
	not container.resources.limits.memory
	msg := sprintf("%s is missing a memory limit", [container.name])
}

deny contains msg if {
	container := containers[_]
	key := object.keys(object.get(container.resources, "requests", {}))[_]
	regex.match(`(?i)gpu`, key)
	msg := sprintf("%s requests a GPU", [container.name])
}

deny contains msg if {
	container := containers[_]
	key := object.keys(object.get(container.resources, "limits", {}))[_]
	regex.match(`(?i)gpu`, key)
	msg := sprintf("%s limits a GPU", [container.name])
}

deny contains msg if {
	container := containers[_]
	not immutable_image(container.image)
	msg := sprintf("%s needs an immutable image tag or digest", [container.name])
}

deny contains msg if {
	container := containers[_]
	env := container.env[_]
	regex.match(`(?i)(SECRET|TOKEN|PASSWORD|API_KEY|DATABASE_URL|PRIVATE_KEY)`, env.name)
	env.value != ""
	msg := sprintf("%s sets %s in the manifest", [container.name, env.name])
}

immutable_image(image) if contains(image, "@")

immutable_image(image) if {
	parts := split(image, "/")
	name := parts[count(parts) - 1]
	contains(name, ":")
	not endswith(name, ":latest")
}
