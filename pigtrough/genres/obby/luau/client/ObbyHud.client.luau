local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local PigTrough = ReplicatedStorage:WaitForChild("PigTrough")
local Config = require(PigTrough:WaitForChild("GameConfig"))
local Hud = require(PigTrough:WaitForChild("Runtime"):WaitForChild("Hud"))

local hud = Hud.new(Config)
local stage = Players.LocalPlayer:WaitForChild("leaderstats"):WaitForChild("Stage")

local function refresh()
	hud:setStatus(("Checkpoint %d / %d"):format(stage.Value, Config.genre.checkpointCount))
end
stage.Changed:Connect(refresh)
refresh()
hud:toast(Config.theme.flavor.intro or "Reach the finish!", 4)
