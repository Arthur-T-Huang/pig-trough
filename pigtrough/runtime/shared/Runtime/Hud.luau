-- Minimal themed HUD built in code: title, status line and toast messages.
-- Toasts are driven by the shared Remotes.Announce event.
local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")

local Hud = {}
Hud.__index = Hud

local function label(parent: Instance, props: { [string]: any }): TextLabel
	local text = Instance.new("TextLabel")
	text.BackgroundTransparency = 1
	text.Font = Enum.Font.FredokaOne
	text.TextScaled = true
	text.TextColor3 = Color3.new(1, 1, 1)
	for key, value in props do
		(text :: any)[key] = value
	end
	local stroke = Instance.new("UIStroke")
	stroke.Thickness = 2
	stroke.Color = Color3.new(0, 0, 0)
	stroke.Transparency = 0.3
	stroke.Parent = text
	text.Parent = parent
	return text
end

function Hud.new(config)
	local palette = config.theme.palette
	local gui = Instance.new("ScreenGui")
	gui.Name = "PigTroughHud"
	gui.ResetOnSpawn = false

	label(gui, {
		Name = "Title",
		Text = config.theme.title,
		TextColor3 = Color3.fromHex(palette.accent),
		Size = UDim2.new(0.5, 0, 0, 40),
		Position = UDim2.new(0.25, 0, 0, 6),
	})
	local status = label(gui, {
		Name = "Status",
		Text = "",
		Size = UDim2.new(0.4, 0, 0, 28),
		Position = UDim2.new(0.3, 0, 0, 48),
	})
	local toast = label(gui, {
		Name = "Toast",
		Text = "",
		TextTransparency = 1,
		TextColor3 = Color3.fromHex(palette.goal),
		Size = UDim2.new(0.6, 0, 0, 48),
		Position = UDim2.new(0.2, 0, 0.3, 0),
	})
	gui.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")

	local self = setmetatable({ gui = gui, status = status, toastLabel = toast, toastId = 0 }, Hud)

	local remotes = script.Parent.Parent:WaitForChild("Remotes")
	remotes:WaitForChild("Announce").OnClientEvent:Connect(function(message: string)
		self:toast(message)
	end)
	return self
end

function Hud:setStatus(text: string)
	self.status.Text = text
end

function Hud:toast(text: string, seconds: number?)
	self.toastId += 1
	local id = self.toastId
	self.toastLabel.Text = text
	self.toastLabel.TextTransparency = 0
	task.delay(seconds or 2.5, function()
		if self.toastId == id then
			TweenService:Create(self.toastLabel, TweenInfo.new(0.5), { TextTransparency = 1 }):Play()
		end
	end)
end

return Hud
