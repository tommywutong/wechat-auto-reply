import AppKit
import Foundation
import SwiftUI

enum AppSection: String, CaseIterable, Identifiable {
    case overview
    case whitelist
    case settings
    case logs

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: return "概览"
        case .whitelist: return "白名单"
        case .settings: return "自动回复设置"
        case .logs: return "运行日志"
        }
    }

    var symbol: String {
        switch self {
        case .overview: return "waveform.path.ecg"
        case .whitelist: return "person.2"
        case .settings: return "slider.horizontal.3"
        case .logs: return "text.alignleft"
        }
    }
}

enum ServiceState: Equatable {
    case running
    case stopped
    case unknown(String)

    var title: String {
        switch self {
        case .running: return "运行中"
        case .stopped: return "已停止"
        case .unknown: return "状态未知"
        }
    }

    var color: Color {
        switch self {
        case .running: return Color(red: 0.08, green: 0.48, blue: 0.36)
        case .stopped: return .secondary
        case .unknown: return .orange
        }
    }

    var symbol: String {
        switch self {
        case .running: return "checkmark.circle.fill"
        case .stopped: return "pause.circle.fill"
        case .unknown: return "questionmark.circle.fill"
        }
    }
}

struct PersonaExample: Codable, Equatable, Identifiable {
    var incoming: String = ""
    var reply: String = ""
    var note: String = ""

    var id: String { "\(incoming)\u{1f}::\(reply)\u{1f}::\(note)" }

    enum CodingKeys: String, CodingKey {
        case incoming = "them"
        case reply = "me"
        case note
    }
}

struct SafeConfig: Codable, Equatable {
    var enabled = true
    var replyMode = "ai"
    var replyToPrivate = true
    var replyToGroup = "only_at_me"
    var selfNicknames: [String] = []
    var allowContacts: [String] = []
    var allowTalkers: [String] = []
    var blockContacts: [String] = []
    var blockKeywords: [String] = []
    var activeHours: [String] = []
    var pollInterval = 5
    var provider = "deepseek"
    var model = "deepseek-chat"
    var maxTokens = 300
    var maxChars = 80
    var personaIdentity = ""
    var personaTone = ""
    var personaPlaybook = ""
    var personaBoundaries: [String] = []
    var personaExamples: [PersonaExample] = []
    var perChatCooldownSeconds = 0
    var maxRepliesPerChatPerDay = 0
    var globalMaxPerHour = 30
    var globalMaxPerDay = 100
    var globalMinIntervalSeconds = 0
    var minDelaySeconds = 0.0
    var maxDelaySeconds = 0.0
    var typingSecondsPerChar = 0.0

    func validationError() -> String? {
        let integerRanges: [(String, Int, ClosedRange<Int>)] = [
            ("轮询间隔", pollInterval, 5...300),
            ("最大输出", maxTokens, 1...10_000),
            ("单条最大字数", maxChars, 1...10_000),
            ("每小时上限", globalMaxPerHour, 1...10_000),
            ("每天上限", globalMaxPerDay, 1...10_000),
            ("单会话每日上限", maxRepliesPerChatPerDay, 0...10_000),
            ("单会话冷却", perChatCooldownSeconds, 0...86_400),
            ("全局最小间隔", globalMinIntervalSeconds, 0...86_400),
        ]
        for (label, value, range) in integerRanges where !range.contains(value) {
            return "\(label)应在 \(range.lowerBound) 到 \(range.upperBound) 之间。"
        }
        let decimalRanges: [(String, Double)] = [
            ("最短等待", minDelaySeconds),
            ("最长等待", maxDelaySeconds),
            ("每字打字时间", typingSecondsPerChar),
        ]
        for (label, value) in decimalRanges where value < 0 || value > 60 {
            return "\(label)应在 0 到 60 之间。"
        }
        if minDelaySeconds > maxDelaySeconds {
            return "最短等待不能大于最长等待。"
        }
        return nil
    }
}

struct TraceMemoSession: Codable, Identifiable, Hashable {
    let talker: String
    let name: String
    let aliases: [String]
    let isGroup: Bool
    let isOfficialAccount: Bool
    let isFolded: Bool
    let isMuted: Bool
    let recentRank: Int?

    var id: String { talker }

    var kindTitle: String {
        if isGroup { return "群聊" }
        if isOfficialAccount { return "公众号" }
        return "私聊"
    }

    var detail: String {
        let suffix = aliases.dropFirst().prefix(2).joined(separator: " / ")
        return suffix.isEmpty ? "\(kindTitle) · \(talker)" : "\(kindTitle) · \(suffix)"
    }
}

struct TraceMemoContactsPayload: Codable {
    let contacts: [TraceMemoSession]
    let count: Int
}

struct TraceMemoNicknamePayload: Codable {
    let candidates: [String]
}

enum SessionCatalog {
    static let recentLimit = 30

    static func searchable(_ sessions: [TraceMemoSession]) -> [TraceMemoSession] {
        sessions.filter { !$0.isOfficialAccount }
    }

    static func recent(_ sessions: [TraceMemoSession], limit: Int = recentLimit) -> [TraceMemoSession] {
        let candidates = searchable(sessions)
        return candidates.enumerated()
            .sorted { lhs, rhs in
                let leftRank = lhs.element.recentRank ?? lhs.offset
                let rightRank = rhs.element.recentRank ?? rhs.offset
                return leftRank < rightRank
            }
            .prefix(max(0, limit))
            .map(\.element)
    }

    static func filter(
        _ sessions: [TraceMemoSession],
        query: String,
        kind: String
    ) -> [TraceMemoSession] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let source = normalizedQuery.isEmpty ? recent(sessions) : searchable(sessions)
        return source.filter { session in
            let kindMatches = kind == "all"
                || (kind == "group" && session.isGroup)
                || (kind == "private" && !session.isGroup)
            guard kindMatches else { return false }
            guard !normalizedQuery.isEmpty else { return true }
            return ([session.name, session.talker] + session.aliases)
                .joined(separator: " ")
                .lowercased()
                .contains(normalizedQuery)
        }
    }
}

enum AppPaths {
    static let serviceLabel = "com.wxauto.tracememo-autoreply"
    static let engineServiceLabel = "com.wxauto.server"

    static func discover() -> URL? {
        let fileManager = FileManager.default
        var candidates: [URL] = []
        if let saved = UserDefaults.standard.string(forKey: "repoPath"), !saved.isEmpty {
            candidates.append(URL(fileURLWithPath: saved))
        }
        if let env = ProcessInfo.processInfo.environment["WXAUTO_REPO_DIR"], !env.isEmpty {
            candidates.append(URL(fileURLWithPath: env))
        }
        var bundle = Bundle.main.bundleURL
        for _ in 0..<4 {
            candidates.append(bundle)
            bundle.deleteLastPathComponent()
        }
        candidates.append(URL(fileURLWithPath: fileManager.currentDirectoryPath))
        return candidates.first(where: isRepository)
    }

    static func isRepository(_ url: URL) -> Bool {
        let scripts = url.appendingPathComponent("scripts/run-tracememo-autoreply.sh")
        let configTemplate = url.appendingPathComponent("core/config.ai.example.yaml")
        return FileManager.default.isReadableFile(atPath: scripts.path)
            && FileManager.default.isReadableFile(atPath: configTemplate.path)
    }
}

struct CommandResult {
    let status: Int32
    let stdout: String
    let stderr: String
}

enum LogFormatter {
    static func merge(stdout: String, stderr: String, limit: Int = 320) -> [String] {
        let standardLines = lines(stdout).map { decorate($0, sourceIsError: false) }
        let errorLines = lines(stderr).map { decorate($0, sourceIsError: true) }
        return Array((standardLines + errorLines).suffix(limit))
    }

    private static func lines(_ value: String) -> [String] {
        guard !value.isEmpty else { return [] }
        return value.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    }

    private static func decorate(_ line: String, sourceIsError: Bool) -> String {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || line.hasPrefix("[错误]") || line.hasPrefix("[警告]") {
            return line
        }

        let upper = line.uppercased()
        if upper.range(of: #"\bDEBUG\b|\bINFO\b"#, options: .regularExpression) != nil {
            return line
        }
        if upper.range(of: #"\bCRITICAL\b|\bERROR\b"#, options: .regularExpression) != nil {
            return "[错误] " + line
        }
        if upper.range(of: #"\bWARNING\b"#, options: .regularExpression) != nil {
            return "[警告] " + line
        }
        // Python logging defaults to stderr. Only unstructured stderr output
        // should inherit the error marker; INFO/DEBUG remain ordinary logs.
        return sourceIsError ? "[错误] " + line : line
    }
}

enum CommandRunner {
    static func run(
        _ executable: String,
        _ arguments: [String],
        cwd: URL? = nil,
        timeout: TimeInterval = 30
    ) -> CommandResult {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.currentDirectoryURL = cwd
        let out = Pipe()
        let err = Pipe()
        final class DataBox {
            var data = Data()
        }
        let stdoutBox = DataBox()
        let stderrBox = DataBox()
        process.standardOutput = out
        process.standardError = err
        do {
            try process.run()
            // Drain both pipes while the child is running. Large TraceMemo
            // contact responses otherwise fill the pipe and deadlock the
            // child before it can exit.
            let readers = DispatchGroup()
            readers.enter()
            DispatchQueue.global(qos: .utility).async {
                stdoutBox.data = out.fileHandleForReading.readDataToEndOfFile()
                readers.leave()
            }
            readers.enter()
            DispatchQueue.global(qos: .utility).async {
                stderrBox.data = err.fileHandleForReading.readDataToEndOfFile()
                readers.leave()
            }
            let deadline = Date(timeIntervalSinceNow: timeout)
            while process.isRunning && Date() < deadline {
                RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05))
            }
            if process.isRunning {
                process.terminate()
                process.waitUntilExit()
                readers.wait()
                return CommandResult(status: -2, stdout: "", stderr: "命令执行超时：\(executable)")
            }
            readers.wait()
            return CommandResult(
                status: process.terminationStatus,
                stdout: String(data: stdoutBox.data, encoding: .utf8) ?? "",
                stderr: String(data: stderrBox.data, encoding: .utf8) ?? ""
            )
        } catch {
            return CommandResult(status: -1, stdout: "", stderr: error.localizedDescription)
        }
    }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var section: AppSection = .overview
    @Published var serviceState: ServiceState = .unknown("正在检查")
    @Published var traceMemoHealthy = false
    @Published var localServerRunning = false
    @Published var traceMemoKeychain = false
    @Published var deepSeekKeychain = false
    @Published var config = SafeConfig()
    @Published private(set) var persistedConfig = SafeConfig()
    @Published var sessions: [TraceMemoSession] = []
    @Published var sessionsLoading = false
    @Published var sessionsError = ""
    @Published var nicknameCandidates: [String] = []
    @Published var nicknameLoading = false
    @Published var logs: [String] = []
    @Published var errorMessage = ""
    @Published var operationMessage = ""
    @Published var isBusy = false
    @Published var lastUpdated = Date()
    @Published var repoURL: URL?

    private var refreshTimer: Timer?
    private var logTimer: Timer?

    init() {
        repoURL = AppPaths.discover()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshStatus() }
        }
        logTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshLogs() }
        }
        refreshStatus()
        refreshLogs()
        loadConfig()
        refreshSessions()
    }

    deinit {
        refreshTimer?.invalidate()
        logTimer?.invalidate()
    }

    var repoName: String { repoURL?.lastPathComponent ?? "未连接项目" }

    var hasUnsavedChanges: Bool { config != persistedConfig }

    var logPath: URL? {
        repoURL?.appendingPathComponent("var/tracememo-autoreply.log")
    }

    var errorLogPath: URL? {
        repoURL?.appendingPathComponent("var/tracememo-autoreply.err.log")
    }

    func chooseRepository() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "选择项目"
        if panel.runModal() == .OK, let url = panel.url {
            guard AppPaths.isRepository(url) else {
                errorMessage = "所选目录不是自动回复项目，缺少启动脚本或配置模板。"
                return
            }
            repoURL = url
            UserDefaults.standard.set(url.path, forKey: "repoPath")
            refreshAll()
        }
    }

    func refreshAll() {
        refreshStatus()
        refreshLogs()
        loadConfig()
        refreshSessions()
    }

    func refreshStatus() {
        guard let repoURL else {
            serviceState = .unknown("请选择项目目录")
            return
        }
        let status = ServiceController.status()
        serviceState = status
        localServerRunning = ServiceController.status(label: AppPaths.engineServiceLabel) == .running
        traceMemoKeychain = ServiceController.keychainExists(service: "com.wxauto.tracememo-api-token")
        deepSeekKeychain = ServiceController.keychainExists(service: "com.wxauto.deepseek-api-key")
        Task { [weak self] in
            let healthy = await HealthCheck.traceMemo()
            await MainActor.run {
                guard let self else { return }
                self.traceMemoHealthy = healthy
                self.lastUpdated = Date()
            }
        }
        _ = repoURL
    }

    func refreshLogs() {
        guard let path = logPath else {
            logs = []
            return
        }
        let primary = CommandRunner.run("/usr/bin/tail", ["-n", "240", path.path]).stdout
        let errors = errorLogPath.map { CommandRunner.run("/usr/bin/tail", ["-n", "120", $0.path]).stdout } ?? ""
        logs = LogFormatter.merge(stdout: primary, stderr: errors)
    }

    func start() { runServiceAction(.start) }
    func stop() { runServiceAction(.stop) }
    func restart() { runServiceAction(.restart) }

    func saveConfig() {
        guard let repoURL else { return }
        if let validationError = config.validationError() {
            errorMessage = validationError
            operationMessage = ""
            return
        }
        isBusy = true
        errorMessage = ""
        operationMessage = "正在保存设置并重启服务…"
        let payload = config
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = ConfigBridge.save(payload, repoURL: repoURL)
            guard result.status == 0 else {
                DispatchQueue.main.async {
                    guard let self else { return }
                    self.isBusy = false
                    self.operationMessage = ""
                    self.errorMessage = result.stderr.isEmpty ? "保存设置失败。" : result.stderr
                }
                return
            }

            // The poller and the HTTP engine are separate launchd jobs. The
            // poller reads scope/limits itself, while the engine keeps the
            // persona, model, and reply policy in memory until it restarts.
            let engineRestart = ServiceController.perform(
                .restart,
                repoURL: repoURL,
                label: AppPaths.engineServiceLabel
            )
            guard engineRestart.status == 0 else {
                DispatchQueue.main.async {
                    guard let self else { return }
                    self.isBusy = false
                    self.operationMessage = "设置已保存，但规则服务重启失败。"
                    self.errorMessage = engineRestart.stderr.isEmpty
                        ? "请手动重启规则服务后再试。"
                        : engineRestart.stderr
                    self.refreshStatus()
                }
                return
            }

            let restart = ServiceController.perform(.restart, repoURL: repoURL)
            let verify = restart.status == 0 ? ConfigBridge.load(repoURL: repoURL) : restart
            DispatchQueue.main.async {
                guard let self else { return }
                self.isBusy = false
                guard restart.status == 0 else {
                    self.operationMessage = "规则服务已更新，但自动回复服务重启失败。"
                    self.errorMessage = restart.stderr.isEmpty ? "请手动重启服务。" : restart.stderr
                    self.refreshStatus()
                    return
                }
                guard verify.status == 0,
                      let data = verify.stdout.data(using: .utf8),
                      let verified = try? JSONDecoder().decode(SafeConfig.self, from: data) else {
                    self.operationMessage = "服务已重启，但无法验证配置是否生效。"
                    self.errorMessage = verify.stderr.isEmpty ? "请打开日志检查配置。" : verify.stderr
                    self.refreshStatus()
                    return
                }
                guard verified == payload else {
                    self.operationMessage = "服务已重启，但回读配置与输入不一致。"
                    self.errorMessage = "请检查输入值后再次保存。"
                    self.config = verified
                    self.persistedConfig = verified
                    self.refreshStatus()
                    return
                }
                self.config = verified
                self.persistedConfig = verified
                self.operationMessage = "设置已保存并生效。\(Date().formatted(date: .omitted, time: .shortened))"
                self.refreshStatus()
            }
        }
    }

    func loadConfig() {
        guard let repoURL else { return }
        let result = ConfigBridge.load(repoURL: repoURL)
        guard result.status == 0, let data = result.stdout.data(using: .utf8) else {
            if !result.stderr.isEmpty { errorMessage = result.stderr }
            return
        }
        do {
            config = try JSONDecoder().decode(SafeConfig.self, from: data)
            persistedConfig = config
        } catch {
            errorMessage = "配置读取失败：\(error.localizedDescription)"
        }
    }

    func suggestSelfNicknames() {
        guard let repoURL else { return }
        nicknameLoading = true
        sessionsError = ""
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = TraceMemoBridge.suggestNicknames(repoURL: repoURL)
            DispatchQueue.main.async {
                guard let self else { return }
                self.nicknameLoading = false
                guard result.status == 0,
                      let data = result.stdout.data(using: .utf8),
                      let payload = try? JSONDecoder().decode(TraceMemoNicknamePayload.self, from: data) else {
                    self.sessionsError = result.stderr.isEmpty ? "TraceMemo 暂时没有返回可确认的昵称。" : result.stderr
                    return
                }
                self.nicknameCandidates = payload.candidates
                if payload.candidates.count == 1, let nickname = payload.candidates.first {
                    self.config.selfNicknames = [nickname]
                    self.operationMessage = "已识别昵称候选“\(nickname)”，保存后用于群聊 @ 判断。"
                } else if payload.candidates.isEmpty {
                    self.sessionsError = "TraceMemo 未提供当前账号昵称，请手动填写。"
                } else {
                    self.operationMessage = "已找到多个昵称候选，请确认后选择一个。"
                }
            }
        }
    }

    private func runServiceAction(_ action: ServiceAction) {
        guard let repoURL else {
            errorMessage = "请先选择项目目录。"
            return
        }
        isBusy = true
        errorMessage = ""
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = ServiceController.perform(action, repoURL: repoURL)
            DispatchQueue.main.async {
                guard let self else { return }
                self.isBusy = false
                if result.status == 0 {
                    self.operationMessage = action.successMessage
                    self.refreshStatus()
                } else {
                    self.errorMessage = result.stderr.isEmpty ? action.failureMessage : result.stderr
                }
            }
        }
    }

    func refreshSessions() {
        guard let repoURL else { return }
        guard !sessionsLoading else { return }
        sessionsLoading = true
        sessionsError = ""
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result = TraceMemoBridge.list(repoURL: repoURL)
            DispatchQueue.main.async {
                guard let self else { return }
                self.sessionsLoading = false
                guard result.status == 0,
                      let data = result.stdout.data(using: .utf8) else {
                    self.sessionsError = result.stderr.isEmpty ? "TraceMemo 会话读取失败。" : result.stderr
                    return
                }
                do {
                    let payload = try JSONDecoder().decode(TraceMemoContactsPayload.self, from: data)
                    self.sessions = payload.contacts
                    self.migrateLegacySelections()
                } catch {
                    self.sessionsError = "TraceMemo 会话数据解析失败：\(error.localizedDescription)"
                }
            }
        }
    }

    var allowedSessionCount: Int {
        if !sessions.isEmpty {
            return SessionCatalog.searchable(sessions).filter(isSessionAllowed).count
        }
        // TraceMemo 暂时不可用时，稳定 talker ID 是规范来源；旧名称只是迁移兼容，不能重复计数。
        if !config.allowTalkers.isEmpty {
            return Set(config.allowTalkers).count
        }
        return Set(config.allowContacts.map(normalizeSessionName)).count
    }

    var searchableSessionCount: Int {
        SessionCatalog.searchable(sessions).count
    }

    var recentSessionCount: Int {
        SessionCatalog.recent(sessions).count
    }

    func isSessionAllowed(_ session: TraceMemoSession) -> Bool {
        if config.allowTalkers.contains(session.talker) {
            return true
        }
        let allowed = Set(config.allowContacts.map(normalizeSessionName))
        return ([session.name] + session.aliases).contains { allowed.contains(normalizeSessionName($0)) }
    }

    func setSessionAllowed(_ session: TraceMemoSession, enabled: Bool) {
        if enabled {
            if !config.allowTalkers.contains(session.talker) {
                config.allowTalkers.append(session.talker)
            }
            let aliases = Set(([session.name] + session.aliases).map(normalizeSessionName))
            if !config.allowContacts.contains(where: { aliases.contains(normalizeSessionName($0)) }) {
                config.allowContacts.append(session.name)
            }
        } else {
            config.allowTalkers.removeAll { $0 == session.talker }
            let aliases = Set(([session.name] + session.aliases).map(normalizeSessionName))
            config.allowContacts.removeAll { aliases.contains(normalizeSessionName($0)) }
        }
    }

    private func migrateLegacySelections() {
        let existing = Set(config.allowTalkers)
        let allowedNames = Set(config.allowContacts.map(normalizeSessionName))
        let migrated = sessions
            .filter { !existing.contains($0.talker) }
            .filter { session in
                ([session.name] + session.aliases).contains { allowedNames.contains(normalizeSessionName($0)) }
            }
            .map(\.talker)
        for talker in migrated where !config.allowTalkers.contains(talker) {
            config.allowTalkers.append(talker)
        }
        if !migrated.isEmpty {
            operationMessage = "已将 \(migrated.count) 个旧名称白名单匹配到稳定会话 ID，保存后完成迁移。"
        }
    }
}

func normalizeSessionName(_ value: String) -> String {
    var result = value
        .replacingOccurrences(of: #"[（(]\s*\d+\s*[)）]\s*$"#, with: "", options: .regularExpression)
        .components(separatedBy: .whitespacesAndNewlines)
        .joined()
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
    while let last = result.last, [".", "。", "．"].contains(String(last)) {
        result.removeLast()
    }
    return result
}

enum ServiceAction {
    case start, stop, restart

    var successMessage: String {
        switch self {
        case .start: return "自动回复服务已启动。"
        case .stop: return "自动回复服务已停止。"
        case .restart: return "自动回复服务已重启。"
        }
    }

    var failureMessage: String {
        switch self {
        case .start: return "启动服务失败"
        case .stop: return "停止服务失败"
        case .restart: return "重启服务失败"
        }
    }
}

enum ServiceController {
    static func domain() -> String { "gui/\(getuid())" }

    static func status(label: String = AppPaths.serviceLabel) -> ServiceState {
        let result = CommandRunner.run("/bin/launchctl", ["print", "\(domain())/\(label)"])
        if result.status != 0 { return .stopped }
        if result.stdout.contains("state = running") || result.stdout.contains("pid = ") {
            return .running
        }
        return .unknown(result.stdout)
    }

    static func perform(
        _ action: ServiceAction,
        repoURL: URL,
        label: String = AppPaths.serviceLabel
    ) -> CommandResult {
        switch action {
        case .stop:
            let result = CommandRunner.run("/bin/launchctl", ["bootout", "\(domain())/\(label)"])
            return result.status == 0 || status(label: label) == .stopped
                ? CommandResult(status: 0, stdout: result.stdout, stderr: "")
                : result
        case .start:
            if status(label: label) != .stopped {
                return CommandRunner.run("/bin/launchctl", ["kickstart", "-k", "\(domain())/\(label)"])
            }
            return bootstrap(repoURL: repoURL, label: label)
        case .restart:
            _ = CommandRunner.run("/bin/launchctl", ["bootout", "\(domain())/\(label)"])
            return bootstrap(repoURL: repoURL, label: label)
        }
    }

    private static func bootstrap(repoURL: URL, label: String) -> CommandResult {
        let plist = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/\(label).plist")
        if FileManager.default.fileExists(atPath: plist.path) {
            let result = CommandRunner.run("/bin/launchctl", ["bootstrap", domain(), plist.path])
            if result.status == 0 { return result }
        }
        guard label == AppPaths.serviceLabel else {
            return CommandResult(
                status: 1,
                stdout: "",
                stderr: "找不到规则服务的 launchd 配置，请先运行 scripts/macos-setup.sh。"
            )
        }
        let install = repoURL.appendingPathComponent("scripts/install-tracememo-autoreply.sh")
        return CommandRunner.run("/bin/bash", [install.path], cwd: repoURL)
    }

    static func keychainExists(service: String) -> Bool {
        CommandRunner.run("/usr/bin/security", ["find-generic-password", "-a", NSUserName(), "-s", service]).status == 0
    }
}

enum ConfigBridge {
    static func python(repoURL: URL) -> String {
        let venv = repoURL.appendingPathComponent(".venv/bin/python")
        return FileManager.default.isExecutableFile(atPath: venv.path) ? venv.path : "/usr/bin/python3"
    }

    static func load(repoURL: URL) -> CommandResult {
        let script = repoURL.appendingPathComponent("scripts/app_config.py")
        return CommandRunner.run(python(repoURL: repoURL), [script.path, "get"], cwd: repoURL)
    }

    static func save(_ config: SafeConfig, repoURL: URL) -> CommandResult {
        let script = repoURL.appendingPathComponent("scripts/app_config.py")
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(config) else {
            return CommandResult(status: 1, stdout: "", stderr: "设置编码失败")
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python(repoURL: repoURL))
        process.arguments = [script.path, "set"]
        process.currentDirectoryURL = repoURL
        let input = Pipe()
        let output = Pipe()
        let error = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = error
        do {
            try process.run()
            input.fileHandleForWriting.write(data)
            input.fileHandleForWriting.closeFile()
            process.waitUntilExit()
            return CommandResult(
                status: process.terminationStatus,
                stdout: String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "",
                stderr: String(data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            )
        } catch {
            return CommandResult(status: -1, stdout: "", stderr: error.localizedDescription)
        }
    }
}

enum TraceMemoBridge {
    static func list(repoURL: URL) -> CommandResult {
        let script = repoURL.appendingPathComponent("scripts/tracememo_contacts.py")
        return CommandRunner.run(
            ConfigBridge.python(repoURL: repoURL),
            [script.path, "list"],
            cwd: repoURL
        )
    }

    static func suggestNicknames(repoURL: URL) -> CommandResult {
        let script = repoURL.appendingPathComponent("scripts/tracememo_contacts.py")
        return CommandRunner.run(
            ConfigBridge.python(repoURL: repoURL),
            [script.path, "suggest-nickname"],
            cwd: repoURL
        )
    }
}

enum HealthCheck {
    static func traceMemo() async -> Bool {
        guard let url = URL(string: "http://127.0.0.1:6131/api/v1/health") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 2
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}

struct StatusLine: View {
    let title: String
    let detail: String
    let state: Bool
    let symbol: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol)
                .foregroundStyle(state ? Color(red: 0.08, green: 0.48, blue: 0.36) : .secondary)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.medium))
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text(state ? "正常" : "未连接")
                .font(.caption.weight(.medium))
                .foregroundStyle(state ? Color(red: 0.08, green: 0.48, blue: 0.36) : .secondary)
        }
    }
}

struct OverviewView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("自动回复").font(.title2.weight(.semibold))
                        Text(model.repoName).font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    ServiceBadge(state: model.serviceState)
                }

                HStack(spacing: 10) {
                    Button { model.start() } label: { Label("启动服务", systemImage: "play.fill") }
                        .buttonStyle(.borderedProminent).tint(Color(red: 0.08, green: 0.48, blue: 0.36))
                        .disabled(model.isBusy || model.serviceState == .running)
                    Button { model.stop() } label: { Label("停止服务", systemImage: "stop.fill") }
                        .buttonStyle(.bordered).disabled(model.isBusy || model.serviceState == .stopped)
                    Button { model.restart() } label: { Label("重启", systemImage: "arrow.clockwise") }
                        .buttonStyle(.bordered).disabled(model.isBusy)
                    Spacer()
                    Button { model.refreshAll() } label: { Label("刷新", systemImage: "arrow.triangle.2.circlepath") }
                        .buttonStyle(.borderless)
                        .help("重新检查服务、权限和日志")
                }

                if !model.errorMessage.isEmpty { Notice(text: model.errorMessage, color: .red, symbol: "exclamationmark.triangle.fill") }
                if !model.operationMessage.isEmpty { Notice(text: model.operationMessage, color: Color(red: 0.08, green: 0.48, blue: 0.36), symbol: "checkmark.circle.fill") }

                VStack(alignment: .leading, spacing: 12) {
                    Text("运行检查").font(.headline)
                    VStack(spacing: 12) {
                        StatusLine(title: "自动回复服务", detail: "launchd · \(AppPaths.serviceLabel)", state: model.serviceState == .running, symbol: "bolt.horizontal.circle")
                        Divider()
                        StatusLine(title: "TraceMemo", detail: "本机 API · 127.0.0.1:6131", state: model.traceMemoHealthy, symbol: "link.circle")
                        Divider()
                        StatusLine(title: "规则服务", detail: "本机 API · 127.0.0.1:8848", state: model.localServerRunning, symbol: "server.rack")
                        Divider()
                        StatusLine(title: "凭据", detail: "macOS Keychain（不会在 App 中显示）", state: model.traceMemoKeychain && model.deepSeekKeychain, symbol: "key.fill")
                    }
                }
                .padding(16)
                .background(Color(nsColor: .windowBackgroundColor), in: RoundedRectangle(cornerRadius: 12))

                HStack(alignment: .top, spacing: 24) {
                    Metric(title: "白名单会话", value: "\(model.allowedSessionCount)", detail: "私信与群聊")
                    Metric(title: "轮询间隔", value: "\(model.config.pollInterval)s", detail: "可在设置调整")
                    Metric(title: "群聊策略", value: groupTitle(model.config.replyToGroup), detail: "当前配置")
                }

                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("最近日志").font(.headline)
                        Spacer()
                        Text("每秒更新").font(.caption).foregroundStyle(.secondary)
                    }
                    LogPreview(lines: Array(model.logs.suffix(8)))
                }
            }
            .padding(24)
        }
    }

    private func groupTitle(_ value: String) -> String {
        switch value { case "never": return "不回复"; case "always": return "全部"; default: return "仅 @我" }
    }
}

struct ServiceBadge: View {
    let state: ServiceState
    var body: some View {
        Label(state.title, systemImage: state.symbol)
            .font(.subheadline.weight(.medium))
            .foregroundStyle(state.color)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(state.color.opacity(0.12), in: Capsule())
    }
}

struct Metric: View {
    let title: String
    let value: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3.weight(.semibold))
            Text(detail).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct Notice: View {
    let text: String
    let color: Color
    let symbol: String
    var body: some View {
        Label(text, systemImage: symbol)
            .font(.subheadline)
            .foregroundStyle(color)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(color.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct LogPreview: View {
    let lines: [String]
    var body: some View {
        Text(lines.isEmpty ? "暂时没有日志" : lines.joined(separator: "\n"))
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
            .lineLimit(8)
    }
}

struct StringListEditor: View {
    let title: String
    let placeholder: String
    @Binding var values: [String]
    @State private var draft = ""

    var body: some View {
        Section(title) {
            if values.isEmpty {
                Text("暂无项目")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(values, id: \.self) { value in
                    HStack(spacing: 8) {
                        Image(systemName: "circle.fill")
                            .font(.system(size: 6))
                            .foregroundStyle(.secondary)
                        Text(value)
                        Spacer()
                        Button("移除", systemImage: "minus.circle") {
                            values.removeAll { $0 == value }
                        }
                        .buttonStyle(.borderless)
                        .foregroundStyle(.red)
                    }
                }
            }
            HStack {
                TextField(placeholder, text: $draft)
                Button("添加", systemImage: "plus") {
                    let value = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !value.isEmpty, !values.contains(value) else { return }
                    values.append(value)
                    draft = ""
                }
                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }
}

struct SessionManagerView: View {
    @ObservedObject var model: AppModel
    @State private var search = ""
    @State private var kind = "all"

    private var filteredSessions: [TraceMemoSession] {
        SessionCatalog.filter(model.sessions, query: search, kind: kind)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("会话管理").font(.title2.weight(.semibold))
                    Text("从 TraceMemo 导入联系人和群聊，使用稳定会话 ID 控制 AI 自动回复。")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                Button("刷新会话", systemImage: "arrow.clockwise") { model.refreshSessions() }
                    .buttonStyle(.bordered)
                    .disabled(model.sessionsLoading)
            }

            HStack(spacing: 10) {
                TextField("搜索名称、备注或会话 ID", text: $search)
                    .textFieldStyle(.roundedBorder)
                Picker("范围", selection: $kind) {
                    Text("全部").tag("all")
                    Text("私聊").tag("private")
                    Text("群聊").tag("group")
                }
                .frame(width: 110)
                Text(search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? "已启用 \(model.allowedSessionCount) · 最近 \(model.recentSessionCount) / \(model.searchableSessionCount)"
                    : "搜索结果 \(filteredSessions.count) / \(model.searchableSessionCount)")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize()
            }

            if !model.sessionsError.isEmpty {
                Notice(text: model.sessionsError, color: .red, symbol: "exclamationmark.triangle.fill")
            }

            if model.sessionsLoading && model.sessions.isEmpty {
                ProgressView("正在读取 TraceMemo 会话…")
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(32)
            } else if filteredSessions.isEmpty {
                Text(model.sessions.isEmpty ? "暂无会话，请确认 TraceMemo 已连接数据库。" : "没有匹配的会话")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(32)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 1) {
                        ForEach(filteredSessions) { session in
                            SessionRow(
                                session: session,
                                isOn: model.isSessionAllowed(session),
                                onChange: { model.setSessionAllowed(session, enabled: $0) }
                            )
                        }
                    }
                }
                .frame(minHeight: 320, maxHeight: 500)
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }
}

struct SessionRow: View {
    let session: TraceMemoSession
    let isOn: Bool
    let onChange: (Bool) -> Void

    var body: some View {
        Toggle(isOn: Binding(get: { isOn }, set: onChange)) {
            HStack(spacing: 10) {
                Image(systemName: session.isGroup ? "person.3" : "person")
                    .foregroundStyle(isOn ? Color(red: 0.08, green: 0.48, blue: 0.36) : .secondary)
                    .frame(width: 22)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(session.name).font(.body.weight(.medium))
                        if session.isOfficialAccount {
                            Text("公众号")
                                .font(.caption2)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 2)
                                .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                        }
                    }
                    Text(session.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .toggleStyle(.switch)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
    }
}

struct WhitelistView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                SessionManagerView(model: model)

                VStack(alignment: .leading, spacing: 12) {
                    Text("消息范围").font(.headline)
                    Toggle("回复私聊", isOn: $model.config.replyToPrivate)
                    Picker("群聊策略", selection: $model.config.replyToGroup) {
                        Text("不回复群聊").tag("never")
                        Text("仅有人 @ 我时回复").tag("only_at_me")
                        Text("群聊消息都回复").tag("always")
                    }
                    TextField("我的微信昵称（用于识别 @）", text: Binding(
                        get: { model.config.selfNicknames.first ?? "" },
                        set: { model.config.selfNicknames = $0.isEmpty ? [] : [$0] }
                    ))
                    HStack(spacing: 8) {
                        Button("从 TraceMemo 识别", systemImage: "wand.and.stars") {
                            model.suggestSelfNicknames()
                        }
                        .buttonStyle(.bordered)
                        .disabled(model.nicknameLoading)
                        if model.nicknameLoading { ProgressView().controlSize(.small) }
                        Text("仅接受 TraceMemo 明确标注为当前账号的候选")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if !model.nicknameCandidates.isEmpty {
                        HStack(spacing: 6) {
                            Text("候选：").font(.caption).foregroundStyle(.secondary)
                            ForEach(model.nicknameCandidates, id: \.self) { candidate in
                                Button(candidate) { model.config.selfNicknames = [candidate] }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                            }
                        }
                    }
                }

                StringListEditor(
                    title: "阻止联系人",
                    placeholder: "添加不会自动回复的联系人",
                    values: $model.config.blockContacts
                )
                StringListEditor(
                    title: "阻止关键词",
                    placeholder: "例如：验证码、转账、密码",
                    values: $model.config.blockKeywords
                )

                HStack {
                    if model.hasUnsavedChanges {
                        Label("有未保存修改", systemImage: "pencil.circle")
                            .font(.caption).foregroundStyle(.orange)
                    } else if !model.isBusy {
                        Label("配置已同步", systemImage: "checkmark.circle")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(model.isBusy ? "保存中…" : "保存并重启", systemImage: model.isBusy ? "hourglass" : "checkmark") { model.saveConfig() }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 0.08, green: 0.48, blue: 0.36))
                        .disabled(model.isBusy)
                }
                if !model.operationMessage.isEmpty {
                    Notice(text: model.operationMessage, color: Color(red: 0.08, green: 0.48, blue: 0.36), symbol: "checkmark.circle.fill")
                }
                if !model.errorMessage.isEmpty {
                    Notice(text: model.errorMessage, color: .red, symbol: "exclamationmark.triangle.fill")
                }
            }
            .padding(24)
        }
        .task {
            if model.sessions.isEmpty { model.refreshSessions() }
        }
    }
}

struct IntSettingField: View {
    let title: String
    let unit: String
    @Binding var value: Int

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            TextField(title, value: $value, format: .number)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
                .frame(width: 92)
            Text(unit).foregroundStyle(.secondary).frame(width: 42, alignment: .leading)
        }
    }
}

struct DoubleSettingField: View {
    let title: String
    let unit: String
    @Binding var value: Double

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            TextField(title, value: $value, format: .number.precision(.fractionLength(0...2)))
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
                .frame(width: 92)
            Text(unit).foregroundStyle(.secondary).frame(width: 42, alignment: .leading)
        }
    }
}

struct PersonaExamplesEditor: View {
    @Binding var examples: [PersonaExample]

    var body: some View {
        Section("示例对话") {
            if examples.isEmpty {
                Text("暂无示例。添加几组真实对话，模型会更容易保持你的口吻。")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ForEach(examples.indices, id: \.self) { index in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("示例 \(index + 1)").font(.subheadline.weight(.medium))
                        Spacer()
                        Button("移除", systemImage: "minus.circle") {
                            examples.remove(at: index)
                        }
                        .buttonStyle(.borderless)
                        .foregroundStyle(.red)
                    }
                    TextField("对方说", text: $examples[index].incoming)
                    TextField("我会回", text: $examples[index].reply)
                    TextField("备注（可选）", text: $examples[index].note)
                }
                .padding(.vertical, 4)
            }
            Button("添加示例", systemImage: "plus") {
                examples.append(PersonaExample())
            }
        }
    }
}

struct SettingsView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Form {
            Section("自动回复") {
                Toggle("启用自动回复", isOn: $model.config.enabled)
                Picker("生成方式", selection: $model.config.replyMode) {
                    Text("AI 生成").tag("ai")
                    Text("仅关键词规则").tag("rules")
                    Text("规则优先，未命中时使用 AI").tag("rules_then_ai")
                }
                IntSettingField(title: "轮询间隔", unit: "秒", value: $model.config.pollInterval)
                Text("间隔越短，发现新消息越及时；最低 5 秒。")
                    .font(.caption).foregroundStyle(.secondary)
            }

            StringListEditor(
                title: "活动时段",
                placeholder: "例如 09:00-23:00，留空表示全天",
                values: $model.config.activeHours
            )

            Section("回复风格") {
                Text("我是谁 / 当前状态").font(.subheadline.weight(.medium))
                TextEditor(text: $model.config.personaIdentity)
                    .frame(minHeight: 60, maxHeight: 120)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.25)))
                Text("说话方式").font(.subheadline.weight(.medium))
                TextEditor(text: $model.config.personaTone)
                    .frame(minHeight: 60, maxHeight: 120)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.25)))
                Text("应对策略").font(.subheadline.weight(.medium))
                TextEditor(text: $model.config.personaPlaybook)
                    .frame(minHeight: 90, maxHeight: 180)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.25)))
                Text("这些内容会作为 AI 的本地系统提示，不会上传到 TraceMemo。")
                    .font(.caption).foregroundStyle(.secondary)
            }

            StringListEditor(
                title: "人格边界",
                placeholder: "例如：不评价第三方，不承诺具体时间",
                values: $model.config.personaBoundaries
            )

            PersonaExamplesEditor(examples: $model.config.personaExamples)

            Section("DeepSeek") {
                LabeledContent("服务商", value: model.config.provider)
                TextField("模型", text: $model.config.model)
                IntSettingField(title: "最大输出", unit: "tokens", value: $model.config.maxTokens)
                Text("API Key 只从 macOS Keychain 读取，App 不显示也不保存密钥。")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section("回复限制") {
                IntSettingField(title: "每小时最多", unit: "条", value: $model.config.globalMaxPerHour)
                IntSettingField(title: "每天最多", unit: "条", value: $model.config.globalMaxPerDay)
                IntSettingField(title: "单会话每日最多（0 为不限）", unit: "条", value: $model.config.maxRepliesPerChatPerDay)
                IntSettingField(title: "单会话冷却", unit: "秒", value: $model.config.perChatCooldownSeconds)
                IntSettingField(title: "全局最小间隔", unit: "秒", value: $model.config.globalMinIntervalSeconds)
                IntSettingField(title: "单条最多", unit: "字", value: $model.config.maxChars)
                DoubleSettingField(title: "最短等待", unit: "秒", value: $model.config.minDelaySeconds)
                DoubleSettingField(title: "最长等待", unit: "秒", value: $model.config.maxDelaySeconds)
                DoubleSettingField(title: "每字打字时间", unit: "秒", value: $model.config.typingSecondsPerChar)
                Text("每日或每会话上限设为 0 表示不限；全局上限仍建议保留。")
                    .font(.caption).foregroundStyle(.secondary)
            }

            Section {
                HStack {
                    if model.hasUnsavedChanges {
                        Label("有未保存修改", systemImage: "pencil.circle")
                            .font(.caption).foregroundStyle(.orange)
                    } else if !model.isBusy {
                        Label("配置已同步", systemImage: "checkmark.circle")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(model.isBusy ? "保存中…" : "保存设置", systemImage: model.isBusy ? "hourglass" : "checkmark") { model.saveConfig() }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 0.08, green: 0.48, blue: 0.36))
                        .disabled(model.isBusy)
                }
                if !model.operationMessage.isEmpty {
                    Notice(text: model.operationMessage, color: Color(red: 0.08, green: 0.48, blue: 0.36), symbol: "checkmark.circle.fill")
                }
                if !model.errorMessage.isEmpty {
                    Notice(text: model.errorMessage, color: .red, symbol: "exclamationmark.triangle.fill")
                }
            }
        }
        .formStyle(.grouped)
        .padding(20)
    }
}

struct LogsView: View {
    @ObservedObject var model: AppModel
    @State private var autoFollow = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("运行日志").font(.title2.weight(.semibold))
                    Text("日志只从本机文件读取，不会上传。\(model.lastUpdated.formatted(date: .omitted, time: .standard)) 更新")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("自动跟随最新", isOn: $autoFollow)
                    .toggleStyle(.checkbox)
                Button("刷新", systemImage: "arrow.clockwise") { model.refreshLogs() }
                    .buttonStyle(.bordered)
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 3) {
                        if model.logs.isEmpty {
                            Text("暂时没有日志")
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            ForEach(Array(model.logs.enumerated()), id: \.offset) { index, line in
                                Text(line.isEmpty ? " " : line)
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .id(index)
                            }
                        }
                    }
                    .padding(12)
                }
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                .onAppear {
                    guard autoFollow, let last = model.logs.indices.last else { return }
                    proxy.scrollTo(last, anchor: .bottom)
                }
                .onReceive(model.$logs) { _ in
                    guard autoFollow, let last = model.logs.indices.last else { return }
                    withAnimation(.easeOut(duration: 0.15)) {
                        proxy.scrollTo(last, anchor: .bottom)
                    }
                }
            }
        }
        .padding(24)
    }
}

struct ContentView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $model.section) { item in
                Label(item.title, systemImage: item.symbol).tag(item)
            }
            .navigationTitle("自动回复")
            .safeAreaInset(edge: .bottom) {
                VStack(alignment: .leading, spacing: 8) {
                    Divider()
                    Button { model.chooseRepository() } label: {
                        Label(model.repoName, systemImage: "folder")
                    }
                    .buttonStyle(.borderless)
                    .help("选择自动回复项目目录")
                }
                .padding(12)
            }
        } detail: {
            switch model.section {
            case .overview: OverviewView(model: model)
            case .whitelist: WhitelistView(model: model)
            case .settings: SettingsView(model: model)
            case .logs: LogsView(model: model)
            }
        }
        .frame(minWidth: 980, minHeight: 650)
    }
}

struct MenuContent: View {
    @ObservedObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(model.serviceState.title, systemImage: model.serviceState.symbol)
                .foregroundStyle(model.serviceState.color)
            Divider()
            Button("打开控制面板", systemImage: "rectangle.on.rectangle") {
                AppDelegate.shared?.showMainWindow()
            }
            Button(model.serviceState == .running ? "停止服务" : "启动服务", systemImage: model.serviceState == .running ? "stop.fill" : "play.fill") {
                if model.serviceState == .running { model.stop() } else { model.start() }
            }
            Button("重启服务", systemImage: "arrow.clockwise") { model.restart() }
            Divider()
            Button("退出 App", systemImage: "power") { NSApp.terminate(nil) }
        }
        .padding(8)
    }
}

@main
struct TraceMemoAutoReplyApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        MenuBarExtra {
            MenuContent(model: appDelegate.model)
        } label: {
            Label("自动回复", systemImage: appDelegate.model.serviceState == .running ? "bolt.fill" : "bolt")
        }
        .menuBarExtraStyle(.menu)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    static weak var shared: AppDelegate?
    let model = AppModel()
    private var mainWindow: NSWindow?

    override init() {
        super.init()
        Self.shared = self
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        DispatchQueue.main.async { [weak self] in
            self?.showMainWindow()
        }
    }

    func showMainWindow() {
        if let mainWindow {
            mainWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let rootView = ContentView(model: model)
        let hosting = NSHostingController(rootView: rootView)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1100, height: 720),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "TraceMemo 自动回复"
        window.minSize = NSSize(width: 980, height: 650)
        window.contentViewController = hosting
        window.center()
        window.isReleasedWhenClosed = false
        mainWindow = window
        NSApp.activate(ignoringOtherApps: true)
        window.orderFrontRegardless()
        window.makeKey()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
