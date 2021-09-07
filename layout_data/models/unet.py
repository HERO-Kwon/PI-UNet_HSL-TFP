import torch
import torch.nn.functional as F
from torch import nn

from layout_data.utils.initialize import initialize_weights


class _EncoderBlock(nn.Module):

    def __init__(self, in_channels, out_channels, dropout=False, polling=True, bn=False):
        super(_EncoderBlock, self).__init__()
        layers = [
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels) if bn else nn.GroupNorm(32, out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels) if bn else nn.GroupNorm(32, out_channels),
            nn.ReLU(inplace=True),
        ]
        if dropout:
            layers.append(nn.Dropout())
        self.encode = nn.Sequential(*layers)
        self.pool = None
        if polling:
            self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

    def forward(self, x):
        if self.pool is not None:
            x = self.pool(x)
        return self.encode(x)


class _DecoderBlock(nn.Module):
    def __init__(self, in_channels, middle_channels, out_channels, bn=False):
        super(_DecoderBlock, self).__init__()
        self.decode = nn.Sequential(
            nn.Conv2d(in_channels, middle_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(middle_channels) if bn else nn.GroupNorm(32, middle_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(middle_channels, middle_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(middle_channels) if bn else nn.GroupNorm(32, middle_channels),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(middle_channels, out_channels, kernel_size=2, stride=2),
        )

    def forward(self, x):
        return self.decode(x)


class UNet(nn.Module):
    def __init__(self, num_classes, in_channels=3, bn=False):
        super(UNet, self).__init__()
        self.enc1 = _EncoderBlock(in_channels, 64, polling=False, bn=bn)
        self.enc2 = _EncoderBlock(64, 128, bn=bn)
        self.enc3 = _EncoderBlock(128, 256, bn=bn)
        self.enc4 = _EncoderBlock(256, 512, bn=bn)
        self.polling = nn.MaxPool2d(kernel_size=2, stride=2)
        self.center = _DecoderBlock(512, 1024, 512, bn=bn)
        self.dec4 = _DecoderBlock(1024, 512, 256, bn=bn)
        self.dec3 = _DecoderBlock(512, 256, 128, bn=bn)
        self.dec2 = _DecoderBlock(256, 128, 64, bn=bn)
        self.dec1 = nn.Sequential(
            nn.Conv2d(128, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64) if bn else nn.GroupNorm(32, 64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64) if bn else nn.GroupNorm(32, 64),
            nn.ReLU(inplace=True),
        )
        self.final = nn.Conv2d(64, num_classes, kernel_size=1)
        initialize_weights(self)

    def forward(self, x):
        enc1 = self.enc1(x)
        enc2 = self.enc2(enc1)
        enc3 = self.enc3(enc2)
        enc4 = self.enc4(enc3)
        center = self.center(self.polling(enc4))
        dec4 = self.dec4(torch.cat([F.interpolate(center, enc4.size()[-2:], mode='bilinear',
                                                  align_corners=True), enc4], 1))
        dec3 = self.dec3(torch.cat([dec4, enc3], 1))
        dec2 = self.dec2(torch.cat([dec3, enc2], 1))
        dec1 = self.dec1(torch.cat([dec2, enc1], 1))
        final = self.final(dec1)
        return final


class _EncoderBlockV2(nn.Module):

    def __init__(self, in_channels, out_channels, dropout=False, polling=True, bn=False):
        super(_EncoderBlockV2, self).__init__()
        layers = [
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, padding_mode='reflect'),
            nn.BatchNorm2d(out_channels) if bn else nn.GroupNorm(32, out_channels),
            nn.GELU(),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, padding_mode='reflect'),
            nn.BatchNorm2d(out_channels) if bn else nn.GroupNorm(32, out_channels),
            nn.GELU(),
        ]
        if dropout:
            layers.append(nn.Dropout())
        self.encode = nn.Sequential(*layers)
        self.pool = None
        if polling:
            self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

    def forward(self, x):
        if self.pool is not None:
            x = self.pool(x)
        return self.encode(x)


class _DecoderBlockV2(nn.Module):
    def __init__(self, in_channels, middle_channels, out_channels, bn=False):
        super(_DecoderBlockV2, self).__init__()
        self.decode = nn.Sequential(
            nn.Conv2d(in_channels, middle_channels, kernel_size=3, padding=1, padding_mode='reflect'),
            nn.BatchNorm2d(middle_channels) if bn else nn.GroupNorm(32, middle_channels),
            nn.GELU(),
            nn.Conv2d(middle_channels, out_channels, kernel_size=3, padding=1, padding_mode='reflect'),
            nn.BatchNorm2d(out_channels) if bn else nn.GroupNorm(32, out_channels),
            nn.GELU()
        )

    def forward(self, x):
        return self.decode(x)


class UNetV2(nn.Module):
    def __init__(self, num_classes, in_channels=3, bn=False, factors=2, multi_scale=True):
        super(UNetV2, self).__init__()
        self.multi_scale = multi_scale
        self.enc1 = _EncoderBlockV2(in_channels, 32 * factors, polling=False, bn=bn)
        self.enc2 = _EncoderBlockV2(32 * factors, 64 * factors, bn=bn)
        self.enc3 = _EncoderBlockV2(64 * factors, 128 * factors, bn=bn)
        self.enc4 = _EncoderBlockV2(128 * factors, 256 * factors, bn=bn)
        self.polling = nn.AvgPool2d(kernel_size=2, stride=2)
        self.center = _DecoderBlockV2(256 * factors, 512 * factors, 256 * factors, bn=bn)
        self.dec4 = _DecoderBlockV2(512 * factors, 256 * factors, 128 * factors, bn=bn)
        self.dec3 = _DecoderBlockV2(256 * factors, 128 * factors, 64 * factors, bn=bn)
        self.dec2 = _DecoderBlockV2(128 * factors, 64 * factors, 32 * factors, bn=bn)
        self.dec1 = nn.Sequential(
            nn.Conv2d(64 * factors, 32 * factors, kernel_size=3, padding=1, padding_mode='reflect'),
            nn.BatchNorm2d(32 * factors) if bn else nn.GroupNorm(32, 32 * factors),
            nn.GELU(),
            nn.Conv2d(32 * factors, 32 * factors, kernel_size=1, padding=0),
            nn.BatchNorm2d(32 * factors) if bn else nn.GroupNorm(32, 32 * factors),
            nn.GELU(),
        )
        if multi_scale:
            self.conv_8 = nn.Conv2d(128 * factors, num_classes, kernel_size=1)
            self.conv_4 = nn.Conv2d(64 * factors, num_classes, kernel_size=1)
            self.conv_2 = nn.Conv2d(32 * factors, num_classes, kernel_size=1)
        self.final = nn.Conv2d(32 * factors, num_classes, kernel_size=1)
        initialize_weights(self)

    def forward(self, x):
        enc1 = self.enc1(x)
        enc2 = self.enc2(enc1)
        enc3 = self.enc3(enc2)
        enc4 = self.enc4(enc3)
        center = self.center(self.polling(enc4))
        dec4 = self.dec4(torch.cat([F.interpolate(center, enc4.size()[-2:], align_corners=False,
                                                  mode='bilinear'), enc4], 1))
        dec3 = self.dec3(torch.cat([F.interpolate(dec4, enc3.size()[-2:], align_corners=False,
                                                  mode='bilinear'), enc3], 1))
        dec2 = self.dec2(torch.cat([F.interpolate(dec3, enc2.size()[-2:], align_corners=False,
                                                  mode='bilinear'), enc2], 1))
        dec1 = self.dec1(torch.cat([F.interpolate(dec2, enc1.size()[-2:], align_corners=False,
                                                  mode='bilinear'), enc1], 1))
        final = self.final(dec1)
        if self.multi_scale:
            return self.conv_8(dec4), self.conv_4(dec3), self.conv_2(dec2), final
        else:
            return final


if __name__ == '__main__':
    model = UNetV2(in_channels=1, num_classes=1)
    print(model)
    x = torch.randn(1, 1, 200, 200)
    with torch.no_grad():
        dec4, dec3, dec2, final = model(x)
        print(dec4.shape, dec3.shape, dec2.shape, final.shape)