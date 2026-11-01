-- Round loop: intermission -> timed collection round -> winner announcement.
-- Round state is published as attributes on ReplicatedStorage.PigTrough for the HUD.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local PigTrough = ReplicatedStorage:WaitForChild("PigTrough")
local Config = require(PigTrough:WaitForChild("GameConfig"))
local Runtime = PigTrough:WaitForChild("Runtime")
local Tagged = require(Runtime:WaitForChild("Tagged"))
local Leaderstats = require(Runtime:WaitForChild("Leaderstats"))
local Announce = PigTrough:WaitForChild("Remotes"):WaitForChild("Announce")

local settings = Config.genre
local collectible: string = settings.collectible
local coinColor = Color3.fromHex(Config.theme.palette.goal)

local coinFolder = Instance.new("Folder")
coinFolder.Name = "Collectibles"
coinFolder.Parent = workspace

local round = 0

local function setState(state: string, duration: number)
	PigTrough:SetAttribute("RoundState", state)
	PigTrough:SetAttribute("RoundEndsAt", workspace:GetServerTimeNow() + duration)
end

local function spawnCoin(roundId: number)
	if roundId ~= round or PigTrough:GetAttribute("RoundState") ~= "Playing" then
		return
	end
	local point = settings.coinSpawns[math.random(#settings.coinSpawns)]
	local coin = Instance.new("Part")
	coin.Name = collectible
	coin.Shape = Enum.PartType.Cylinder
	coin.Size = Vector3.new(0.6, 3, 3)
	coin.Anchored = true
	coin.CanCollide = false
	coin.Material = Enum.Material.Neon
	coin.Color = coinColor
	coin.CFrame = CFrame.new(point[1], point[2], point[3])
	coin:SetAttribute("SpinSpeed", 180)
	coin:AddTag("Spinner")

	local taken = false
	coin.Touched:Connect(function(hit)
		local player = Tagged.playerFromHit(hit)
		if taken or not player then
			return
		end
		taken = true
		Leaderstats.add(player, collectible, 1)
		coin:Destroy()
		task.delay(settings.coinRespawnSeconds, spawnCoin, roundId)
	end)
	coin.Parent = coinFolder
end

local function playRound()
	round += 1
	for _, player in Players:GetPlayers() do
		local stat = Leaderstats.get(player, collectible)
		if stat then
			stat.Value = 0
		end
	end
	setState("Playing", settings.roundSeconds)
	Announce:FireAllClients(("Collect the %s!"):format(collectible))
	for _ = 1, settings.coinCount do
		spawnCoin(round)
	end
	task.wait(settings.roundSeconds)

	setState("Ended", 0)
	coinFolder:ClearAllChildren()
	local best, bestScore = nil, 0
	for _, player in Players:GetPlayers() do
		local stat = Leaderstats.get(player, collectible)
		if stat and stat.Value > bestScore then
			best, bestScore = player, stat.Value
		end
	end
	if best then
		Leaderstats.add(best, "Wins", 1)
		Announce:FireAllClients(("%s wins with %d %s!"):format(best.DisplayName, bestScore, collectible))
	else
		Announce:FireAllClients("Nobody scored this round")
	end
end

local function onPlayer(player: Player)
	Leaderstats.setup(player, { collectible, "Wins" })
end
Players.PlayerAdded:Connect(onPlayer)
for _, player in Players:GetPlayers() do
	onPlayer(player)
end

while true do
	setState("Intermission", settings.intermissionSeconds)
	task.wait(settings.intermissionSeconds)
	playRound()
end
