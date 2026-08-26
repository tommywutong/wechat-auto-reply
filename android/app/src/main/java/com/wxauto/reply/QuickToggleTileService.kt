package com.wxauto.reply

import android.graphics.drawable.Icon
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.wxauto.reply.engine.Storage

/**
 * 下拉通知栏里的快捷开关。
 *
 * 为什么值得单独做：自动回复是个「需要时打开、不需要就关掉」的功能，
 * 每次都去打开 App 点开关太重。加到快捷设置面板后，
 * 下拉两下点一下就切换，和开关手电筒一样方便。
 *
 * 用户需要手动把它拖进快捷设置面板：
 * 下拉通知栏 → 编辑（铅笔图标）→ 找到「微信自动回复」拖上去。
 */
class QuickToggleTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        refresh()
    }

    override fun onClick() {
        super.onClick()
        val next = !Storage.loadConfig(this).enabled
        Storage.setEnabled(this, next)
        refresh()
    }

    private fun refresh() {
        val tile = qsTile ?: return
        val enabled = Storage.loadConfig(this).enabled

        tile.state = if (enabled) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = getString(R.string.app_name)
        tile.contentDescription = getString(
            if (enabled) R.string.tile_on else R.string.tile_off
        )
        tile.icon = Icon.createWithResource(this, R.drawable.ic_tile)
        // Android 10+ 才有副标题，低版本忽略
        runCatching {
            tile.subtitle = getString(if (enabled) R.string.tile_on else R.string.tile_off)
        }
        tile.updateTile()
    }
}
