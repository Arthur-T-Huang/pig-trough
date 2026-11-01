local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local PigTrough = ReplicatedStorage:WaitForChild("PigTrough")
local Config = require(PigTrough:WaitForChild("GameConfig"))
local Hud = require(PigTrough:WaitForChild("Runtime"):WaitForChild("Hud"))

local collectible: string = Config.genre.collectible
local hud = Hud.new(Config)
local score = Players.LocalPlayer:WaitForChild("leaderstats"):WaitForChild(collectible)
hud:toast(Config.theme.flavor.intro or ("Collect the most %s!"):format(collectible), 4)

while true do
	local state = PigTrough:GetAttribute("RoundState")
	local remaining = math.max(0, math.ceil((PigTrough:GetAttribute("RoundEndsAt") or 0) - workspace:GetServerTimeNow()))
	local clock = ("%d:%02d"):format(remaining // 60, remaining % 60)
	if state == "Playing" then
		hud:setStatus(("%s  |  %d %s"):format(clock, score.Value, collectible))
	elseif state == "Intermission" then
		hud:setStatus("Next round in " .. clock)
	else
		hud:setStatus("Round over")
	end
	task.wait(0.2)
end
