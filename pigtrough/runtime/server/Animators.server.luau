-- Generic tag-driven motion for generated maps:
--   Mover   : oscillates between its CFrame and CFrame + MoveOffset (Vector3) every MovePeriod seconds
--   Spinner : rotates about its Y axis at SpinSpeed degrees/second
--   Fader   : fades out FadeDelay seconds after being stepped on, returns after FadeRespawn
-- Movers/spinners also set assembly velocity so characters standing on them are carried along.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Tagged = require(ReplicatedStorage:WaitForChild("PigTrough"):WaitForChild("Runtime"):WaitForChild("Tagged"))

local movers: { [BasePart]: { origin: CFrame, offset: Vector3, period: number, phase: number } } = {}
local spinners: { [BasePart]: { origin: CFrame, speed: number } } = {}

local function track(registry: { [BasePart]: any }, part: BasePart, data: any)
	registry[part] = data
	part.Destroying:Connect(function()
		registry[part] = nil
	end)
end

Tagged.each("Mover", function(part)
	if part:IsA("BasePart") then
		track(movers, part, {
			origin = part.CFrame,
			offset = part:GetAttribute("MoveOffset") or Vector3.new(10, 0, 0),
			period = part:GetAttribute("MovePeriod") or 4,
			phase = part:GetAttribute("MovePhase") or 0,
		})
	end
end)

Tagged.each("Spinner", function(part)
	if part:IsA("BasePart") then
		track(spinners, part, {
			origin = part.CFrame,
			speed = math.rad(part:GetAttribute("SpinSpeed") or 90),
		})
	end
end)

Tagged.each("Fader", function(part)
	if not part:IsA("BasePart") then
		return
	end
	local busy = false
	local opaque = part.Transparency
	part.Touched:Connect(function(hit)
		if busy or not (hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")) then
			return
		end
		busy = true
		local delay = part:GetAttribute("FadeDelay") or 0.6
		TweenService:Create(part, TweenInfo.new(delay), { Transparency = 0.85 }):Play()
		task.wait(delay)
		part.CanCollide = false
		part.Transparency = 1
		task.wait(part:GetAttribute("FadeRespawn") or 2.5)
		part.CanCollide = true
		part.Transparency = opaque
		busy = false
	end)
end)

RunService.Heartbeat:Connect(function()
	local t = workspace:GetServerTimeNow()
	for part, m in movers do
		local w = 2 * math.pi / m.period
		local s = math.sin(w * t + m.phase)
		part.CFrame = m.origin + m.offset * (0.5 + 0.5 * s)
		part.AssemblyLinearVelocity = m.offset * (0.5 * w * math.cos(w * t + m.phase))
	end
	for part, s in spinners do
		part.CFrame = s.origin * CFrame.Angles(0, (s.speed * t) % (2 * math.pi), 0)
		part.AssemblyAngularVelocity = Vector3.new(0, s.speed, 0)
	end
end)
